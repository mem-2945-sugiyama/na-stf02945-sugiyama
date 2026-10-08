# /// script
# requires-python = ">=3.12"
# dependencies = [
#     # 社内ネットワークの SSL 証明書(自己署名)を Python が信頼できないため、
#     # macOS のキーチェーンの証明書で検証させる
#     "truststore>=0.9",
# ]
# ///
"""その日の活動を集め、Claude Code(claude -p)で日報を自動作成して nippo に保存する。

ローカルの Mac で実行する。手順:
  1. Claude Code のセッションログを取り込む
  2. Google カレンダーの予定を取り込む(ダウンロードフォルダのエクスポート・iCal URL・claude.ai のコネクタ)
  3. nippo に登録済みの活動(手入力メモ・Slack 貼り付けを含む)を取得する
  4. claude -p に渡して4セクションの日報を書かせ、nippo に保存する

使い方:
    uv run importer/nippo_auto.py                    # 今日の日報を作成
    uv run importer/nippo_auto.py --date 2026-10-07
    uv run importer/nippo_auto.py --dry-run          # Claude に渡すプロンプトを表示するだけ
"""

import argparse
import datetime as dt
import glob
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import truststore

import calendar_connector
import claude_logs

truststore.inject_into_ssl()

JST = claude_logs.JST
CONFIG_PATH = Path.home() / ".config" / "nippo" / "config.toml"
HEADINGS = (
    "今日やったこと",
    "技術的に学んだこと",
    "ビジネス・ヒューマンスキルで学んだこと",
    "今日の一言",
)
SOURCE_LABELS = {
    "manual": "手入力メモ",
    "claude": "Claude Code での作業",
    "calendar": "カレンダーの予定",
    "slack": "Slack の投稿",
}
CATEGORY_LABELS = {
    "work": "作業",
    "meeting": "会議",
    "tech_learning": "技術の学び",
    "business_learning": "ビジネスの学び",
}
# プロンプトが長すぎると応答が遅く利用枠も消費するため、1件の詳細と全体に上限を設ける。
# Claude ログは依頼・回答・変更ファイルの抜粋を含み、Slack 貼り付けは1日分が1件にまとまるため、
# この2つは上限を大きくする
DETAIL_LIMITS = {"claude": 6000, "slack": 8000}
DEFAULT_DETAIL_LIMIT = 1500
MAX_MATERIAL_CHARS = 60_000
# 全体の上限で切り詰めるときは末尾から削れるため、必ず反映させたい手入力メモを先頭に置き、
# 量が多く削れても影響の小さい Claude ログを最後にする
SOURCE_ORDER = ("manual", "calendar", "slack", "claude")

# 日報の書き方の指示。フォーマットや言い回しを調整しやすいよう別ファイルにしている。
# {date}・{comment}・{materials} が差し込まれる
PROMPT_PATH = Path(__file__).with_name("nippo_prompt.txt")
# 作成済みの日報を短く書き直すときの指示。{body} が差し込まれる
SHORTEN_PROMPT_PATH = Path(__file__).with_name("shorten_prompt.txt")


def load_config(path: Path = CONFIG_PATH) -> dict:
    """設定ファイルを読む。無ければ空の設定を返す。"""
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def find_claude(configured: str | None) -> str:
    """claude コマンドのパスを返す。見つからなければ FileNotFoundError を送出する。

    優先順位: 設定ファイル → PATH → VS Code 拡張に同梱のもの(最新版)。
    """
    if configured:
        return configured
    if found := shutil.which("claude"):
        return found
    pattern = str(
        Path.home() / ".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"
    )
    candidates = sorted(glob.glob(pattern), key=_extension_version)
    if candidates:
        return candidates[-1]
    raise FileNotFoundError(
        "claude コマンドが見つかりません。設定ファイルの [claude] path で指定してください"
    )


def _extension_version(path: str) -> tuple[int, ...]:
    # 文字列のままだと 2.1.99 が 2.1.281 より新しいと判定されるため、数値で比較する
    match = re.search(r"anthropic\.claude-code-([\d.]+)", path)
    return tuple(int(n) for n in match.group(1).split(".")) if match else ()


def api_request(api: str, method: str, path: str, body: object = None) -> object:
    """nippo API に JSON でリクエストする。404 は None を返し、それ以外の失敗は例外を送出する。"""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{api.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as res:
            return json.load(res) if res.status != 204 else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


# Google カレンダーの「エクスポート」でダウンロードされるファイル(.ics を束ねた zip)と、単体の .ics。
# 先に書いたパターンを優先する(ダウンロードフォルダには会議の招待状など単体の .ics も入りやすく、
# それが新しいからといってエクスポート全体の代わりに使うと予定の大半が漏れるため)
DEFAULT_EXPORT_PATTERNS = ("*.ical.zip", "*.ics")


def find_calendar_export(directory: Path, day: dt.date, patterns: list[str]) -> Path | None:
    """directory にあるカレンダーのエクスポートのうち、使うべき1件を返す。無ければ None。

    day(JST)以降に保存されたものに限る(それより前のエクスポートには当日追加された予定が無いため)。
    patterns は優先順で、最初に該当があったパターンの中で最新のものを選ぶ。
    """
    day_start = dt.datetime.combine(day, dt.time(), tzinfo=JST)
    for pattern in patterns:
        candidates = []
        for path in directory.glob(pattern):
            modified = dt.datetime.fromtimestamp(path.stat().st_mtime, JST)
            if modified >= day_start:
                candidates.append((modified, path))
        if candidates:
            return max(candidates)[1]
    return None


def import_calendar_url(api: str, url: str, day: dt.date) -> int:
    """iCal URL の内容を取得して nippo に取り込む。取り込んだ件数を返す。"""
    with urllib.request.urlopen(url, timeout=30) as res:
        return upload_calendar(api, res.read(), day)


def upload_calendar(api: str, ics: bytes, day: dt.date) -> int:
    """.ics(または Google のエクスポート zip)を nippo の取り込み API に渡す。取り込んだ件数を返す。"""
    # 解析(zip の展開・繰り返し予定の展開・日付の絞り込み)はサーバー側の実装を再利用するため、
    # 画面のアップロードと同じ API にそのまま送る
    boundary = uuid.uuid4().hex
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="calendar.ics"\r\n'
            "Content-Type: text/calendar\r\n\r\n"
        ).encode()
        + ics
        + f"\r\n--{boundary}--\r\n".encode()
    )
    query = urllib.parse.urlencode({"date": day.isoformat()})
    request = urllib.request.Request(
        f"{api.rstrip('/')}/api/imports/ics?{query}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as res:
        return json.load(res)["imported"]


def format_materials(activities: list[dict]) -> str:
    """活動の一覧を、取り込み元ごとに見出しを付けたテキストにする。"""
    sections: dict[str, list[str]] = {}
    for a in activities:
        lines = [f"- {a['title']}"]
        if a["source"] == "manual":
            lines[0] += f"(分類: {CATEGORY_LABELS.get(a['category'], a['category'])})"
        if a.get("project"):
            lines.append(f"  プロジェクト: {a['project']}")
        if a.get("detail"):
            limit = DETAIL_LIMITS.get(a["source"], DEFAULT_DETAIL_LIMIT)
            detail = claude_logs.truncate(a["detail"], limit)
            lines.append("  " + detail.replace("\n", "\n  "))
        sections.setdefault(a["source"], []).extend(lines)
    text = "\n\n".join(
        f"## {SOURCE_LABELS.get(source, source)}\n" + "\n".join(lines)
        for source, lines in sorted(sections.items(), key=lambda kv: _source_rank(kv[0]))
    )
    return claude_logs.truncate(text, MAX_MATERIAL_CHARS) if text else "(記録なし)"


def _source_rank(source: str) -> int:
    return SOURCE_ORDER.index(source) if source in SOURCE_ORDER else len(SOURCE_ORDER)


def build_prompt(day: dt.date, activities: list[dict], comment: str) -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").format(
        date=day.isoformat(),
        comment=comment.strip() or "(なし)",
        materials=format_materials(activities),
    )


def run_claude(claude: str, prompt: str, model: str) -> str:
    """claude -p で日報本文を生成する。失敗時は RuntimeError を送出する。"""
    # ツールを無効にする: 活動記録(カレンダー・Slack など外部由来の文章)に指示が紛れ込んでも、
    # ファイル操作やコマンド実行につながらないようにするため。
    # セッションを保存しない: 保存すると次回の Claude ログ取り込みで、この生成処理自体が
    # 「作業」として日報に載ってしまうため。
    # 作業ディレクトリを一時ディレクトリにする: リポジトリの CLAUDE.md などを読み込ませないため
    with tempfile.TemporaryDirectory() as workdir:
        result = subprocess.run(
            [claude, "-p", "--no-session-persistence", "--tools", "", "--model", model],
            input=prompt,
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=300,
        )
    if result.returncode != 0:
        raise RuntimeError(f"claude の実行に失敗しました: {result.stderr.strip()[:500]}")
    body = result.stdout.strip()
    if not body.startswith(HEADINGS[0]) or any(h not in body for h in HEADINGS):
        raise RuntimeError(f"日報の形式になっていない応答です:\n{body[:500]}")
    return body + "\n"


class NippoError(Exception):
    """日報の作成に失敗したことを表す。

    生成までは成功して保存だけ失敗した場合、生成した本文を unsaved_body に持つ
    (利用枠を使って作った本文を呼び出し側で失わずに済むようにするため)。
    """

    def __init__(self, message: str, unsaved_body: str | None = None):
        super().__init__(message)
        self.unsaved_body = unsaved_body


def collect_materials(
    day: dt.date, config: dict, *, use_connector: bool = True
) -> tuple[list, str]:
    """各取り込み元から nippo に取り込み、登録済みの活動と今日の一言を返す。

    進捗は標準出力、取り込み元ごとの失敗は警告として標準エラーに出し、処理は続ける。
    nippo API に接続できない・エラーを返した場合は NippoError を送出する。
    """
    api = config.get("api", "http://localhost:8000")
    claude_config = config.get("claude", {})
    calendar_config = config.get("calendar", {})
    try:
        # 1. Claude Code のログ
        sessions = claude_logs.collect(day)
        if sessions:
            result = claude_logs.post(api, [claude_logs.to_activity(s, day) for s in sessions])
            print(f"Claude ログ: 新規 {result['created']} 件 / 更新 {result['updated']} 件")

        # 2. Google カレンダー(ダウンロードフォルダのエクスポート)
        export_dir = Path(calendar_config.get("export_dir", "~/Downloads")).expanduser()
        export = find_calendar_export(
            export_dir,
            day,
            calendar_config.get("export_patterns", list(DEFAULT_EXPORT_PATTERNS)),
        )
        if export:
            try:
                count = upload_calendar(api, export.read_bytes(), day)
                print(f"カレンダー({export.name}): {count} 件")
            except urllib.error.HTTPError as e:
                print(f"警告: {export.name} を取り込めません({e.code})", file=sys.stderr)
        else:
            print(f"カレンダー: {export_dir} に {day} 以降のエクスポートがないため取り込みません")

        # 2'. Google カレンダー(iCal URL)
        for url in calendar_config.get("ical_urls", []):
            try:
                print(f"カレンダー(iCal URL): {import_calendar_url(api, url, day)} 件")
            except (urllib.error.URLError, OSError) as e:
                # URL は秘密情報のため表示しない。1つ失敗しても他の材料で日報は作る
                print(f"警告: カレンダーを取得できません: {e}", file=sys.stderr)

        # 2''. Google カレンダー(claude.ai のコネクタ経由)
        connector_tools = calendar_config.get("connector_tools", [])
        if connector_tools and use_connector:
            try:
                events = calendar_connector.fetch_events(
                    find_claude(claude_config.get("path")),
                    day,
                    claude_config.get("calendar_model", "haiku"),
                    connector_tools,
                )
                if events:
                    claude_logs.post(api, events)
                print(f"カレンダー(コネクタ): {len(events)} 件")
            except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as e:
                # カレンダーが取れなくても他の材料で日報は作る
                print(f"警告: カレンダーを取得できません: {e}", file=sys.stderr)

        # 3. 登録済みの活動と、本人が入力した今日の一言
        activities = api_request(api, "GET", f"/api/activities?date={day.isoformat()}") or []
        report = api_request(api, "GET", f"/api/reports/{day.isoformat()}")
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode(errors="replace")
        raise NippoError(f"nippo API がエラーを返しました({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise NippoError(f"nippo API({api})に接続できません: {e}") from e
    return activities, (report or {}).get("comment", "")


def generate_report(day: dt.date, config: dict) -> str:
    """材料を集めて Claude で日報を作成し、nippo に保存して本文を返す。

    失敗時は NippoError を送出する(保存だけ失敗した場合は unsaved_body に本文が入る)。
    """
    activities, comment = collect_materials(day, config)
    claude_config = config.get("claude", {})
    try:
        claude = find_claude(claude_config.get("path"))
        print("Claude で日報を作成中...")
        body = run_claude(
            claude, build_prompt(day, activities, comment), claude_config.get("model", "sonnet")
        )
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as e:
        raise NippoError(str(e)) from e
    try:
        api = config.get("api", "http://localhost:8000")
        api_request(
            api, "PUT", f"/api/reports/{day.isoformat()}", {"body": body, "comment": comment}
        )
    except urllib.error.URLError as e:
        raise NippoError(f"日報を保存できませんでした: {e}", unsaved_body=body) from e
    return body


def shorten_report(body: str, config: dict) -> str:
    """日報の本文を Claude で短く書き直して返す(保存はしない)。

    手直し済みの本文をそのまま活かすため、材料の取り込みはやり直さない。
    失敗時は NippoError を送出する。
    """
    claude_config = config.get("claude", {})
    prompt = SHORTEN_PROMPT_PATH.read_text(encoding="utf-8").format(body=body.strip())
    try:
        return run_claude(
            find_claude(claude_config.get("path")), prompt, claude_config.get("model", "sonnet")
        )
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as e:
        raise NippoError(str(e)) from e


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=dt.date.fromisoformat, default=dt.datetime.now(JST).date())
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument(
        "--dry-run", action="store_true", help="取り込みのあと、プロンプトを表示して終了"
    )
    args = parser.parse_args(argv)
    config = load_config(args.config)

    try:
        if args.dry_run:
            activities, comment = collect_materials(args.date, config, use_connector=False)
            print(build_prompt(args.date, activities, comment))
            return 0
        body = generate_report(args.date, config)
    except NippoError as e:
        if e.unsaved_body:
            print(e.unsaved_body)
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    print(body)
    print(f"{args.date} の日報を保存しました。画面の「再読み込み」で確認・コピーできます")
    return 0


if __name__ == "__main__":
    sys.exit(main())
