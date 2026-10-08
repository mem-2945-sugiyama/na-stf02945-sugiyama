# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Claude Code のセッションログから指定日の作業を集計し、nippo API に取り込む。

ローカルの Mac で実行する(ログは ~/.claude にあり、サーバーからは読めないため)。
標準ライブラリだけで動くようにしている。`uv run` でも `python3` でも実行できる。

使い方:
    uv run importer/claude_logs.py                       # 今日の分を取り込む
    uv run importer/claude_logs.py --date 2026-10-07 --dry-run
"""

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# <system-reminder>…</system-reminder> や <command-name>…</command-name> など、
# Claude Code が依頼文に差し込むタグは本人の依頼ではないため中身ごと除く
_TAG_BLOCK = re.compile(r"<([a-zA-Z][\w-]*)\b[^>]*>.*?</\1>", re.S)
_NOISE_PROMPTS = {"[Request interrupted by user]", "[Request interrupted by user for tool use]"}

MAX_PROMPTS_IN_DETAIL = 10
MAX_PROMPT_CHARS = 200
MAX_FILES_IN_DETAIL = 20
MAX_TITLE_CHARS = 60
# 「学んだこと」を AI が書く材料として、Claude の回答も抜粋して残す。
# 短い相槌(「確認します」等)は材料にならないため一定の長さ以上に限る。
# 長い回答ほど説明・調査結果を含むことが多いため、件数を絞るときは長いものを優先する
MIN_ANSWER_CHARS = 80
MAX_ANSWERS_IN_DETAIL = 8
MAX_ANSWER_CHARS = 400


@dataclass
class SessionSummary:
    session_id: str
    cwd: str = ""
    first_at: dt.datetime | None = None
    last_at: dt.datetime | None = None
    title: str | None = None
    prompts: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    files: dict[str, None] = field(default_factory=dict)  # 順序付きの集合として使う

    def touch(self, at: dt.datetime) -> None:
        if self.first_at is None or at < self.first_at:
            self.first_at = at
        if self.last_at is None or at > self.last_at:
            self.last_at = at


def collect(day: dt.date, projects_dir: Path = DEFAULT_PROJECTS_DIR) -> list[SessionSummary]:
    """day(JST)に活動があったセッションを、開始時刻順に返す。

    projects_dir 直下の各プロジェクトの *.jsonl だけを読む(subagents/ 配下は対象外)。
    読めない行・ファイルは読み飛ばす。
    """
    day_start = dt.datetime.combine(day, dt.time(), tzinfo=JST)
    sessions: dict[str, SessionSummary] = {}
    for path in sorted(projects_dir.glob("*/*.jsonl")):
        try:
            # ログは数十 MB になるため、対象日より前に更新が止まったファイルは開かない
            if dt.datetime.fromtimestamp(path.stat().st_mtime, JST) < day_start:
                continue
            _read_file(path, day, sessions)
        except OSError as e:
            print(f"警告: {path} を読めません: {e}", file=sys.stderr)
    active = [s for s in sessions.values() if s.first_at is not None]
    return sorted(active, key=lambda s: s.first_at)


def _read_file(path: Path, day: dt.date, sessions: dict[str, SessionSummary]) -> None:
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # 書き込み途中の行や形式変更に備え、壊れた行は無視して続ける
                continue
            if isinstance(record, dict):
                _apply(record, day, sessions)


def _apply(record: dict, day: dt.date, sessions: dict[str, SessionSummary]) -> None:
    session_id = record.get("sessionId")
    if not session_id or record.get("isSidechain"):
        return
    session = sessions.setdefault(session_id, SessionSummary(session_id))

    # タイトルは日付に関係なくセッションの最新のものを使う(タイムスタンプを持たないレコードのため)
    if record.get("type") == "ai-title" and record.get("aiTitle"):
        session.title = str(record["aiTitle"]).strip()
        return

    at = _parse_timestamp(record.get("timestamp"))
    if at is None or at.date() != day:
        return
    if record.get("type") not in ("user", "assistant"):
        return
    session.touch(at)
    # 作業中に cd でサブディレクトリへ移ることがあるため、最初の cwd をプロジェクトとする
    if record.get("cwd") and not session.cwd:
        session.cwd = record["cwd"]

    content = (record.get("message") or {}).get("content")
    if record["type"] == "user":
        prompt = _extract_prompt(record, content)
        if prompt:
            session.prompts.append(prompt)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                answer = re.sub(r"\s+", " ", block.get("text", "")).strip()
                if len(answer) >= MIN_ANSWER_CHARS:
                    session.answers.append(answer)
            if isinstance(block, dict) and block.get("type") == "tool_use":
                if block.get("name") in EDIT_TOOLS:
                    params = block.get("input") or {}
                    file_path = params.get("file_path") or params.get("notebook_path")
                    if file_path:
                        session.files[str(file_path)] = None


def _parse_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(JST)


def _extract_prompt(record: dict, content: object) -> str | None:
    """本人が入力した依頼文だけを返す。ツール結果・メタ情報・差し込みタグは除く。"""
    if record.get("isMeta"):
        return None
    if isinstance(content, str):
        texts = [content]
    elif isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        texts = [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ]
    else:
        return None
    text = " ".join(_TAG_BLOCK.sub("", t) for t in texts)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text in _NOISE_PROMPTS:
        return None
    return text


def sample_evenly(items: list[str], limit: int) -> list[str]:
    """先頭から末尾まで等間隔に limit 件選ぶ。

    先頭だけを取ると、長いセッションの後半の作業が日報の材料から漏れるため。
    limit が 1 以下の場合は先頭から limit 件(0 以下なら空)を返す。
    """
    if len(items) <= limit:
        return items
    if limit <= 1:
        return items[: max(limit, 0)]
    step = (len(items) - 1) / (limit - 1)
    return [items[round(i * step)] for i in range(limit)]


def longest_in_order(items: list[str], limit: int) -> list[str]:
    """長い順に limit 件選び、元の順序で返す。"""
    keep = sorted(range(len(items)), key=lambda i: len(items[i]), reverse=True)[:limit]
    return [items[i] for i in sorted(keep)]


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def to_activity(session: SessionSummary, day: dt.date) -> dict:
    """セッションを nippo API の取り込み形式(ActivityImport)に変換する。"""
    base = session.title or (session.prompts[0] if session.prompts else "Claude Code での作業")
    title = truncate(base, MAX_TITLE_CHARS)
    if session.files:
        title += f"(変更 {len(session.files)} ファイル)"

    detail_lines: list[str] = []
    if session.prompts:
        detail_lines.append("依頼:")
        detail_lines += [
            f"- {truncate(p, MAX_PROMPT_CHARS)}"
            for p in sample_evenly(session.prompts, MAX_PROMPTS_IN_DETAIL)
        ]
    if session.answers:
        detail_lines.append("Claude の回答(抜粋):")
        detail_lines += [
            f"- {truncate(a, MAX_ANSWER_CHARS)}"
            for a in longest_in_order(session.answers, MAX_ANSWERS_IN_DETAIL)
        ]
    if session.files:
        detail_lines.append("変更ファイル:")
        detail_lines += [
            f"- {_relative(p, session.cwd)}" for p in list(session.files)[:MAX_FILES_IN_DETAIL]
        ]

    return {
        "date": day.isoformat(),
        "category": "work",
        "title": title,
        "project": Path(session.cwd).name if session.cwd else None,
        "detail": "\n".join(detail_lines) or None,
        "started_at": session.first_at.isoformat(),
        "ended_at": session.last_at.isoformat(),
        "source": "claude",
        # 日をまたぐセッションを日ごとに別の活動として扱うため、日付を含める
        "external_id": f"{session.session_id}@{day.isoformat()}",
    }


def _relative(file_path: str, cwd: str) -> str:
    try:
        return str(Path(file_path).relative_to(cwd)) if cwd else file_path
    except ValueError:
        return file_path


def post(api: str, activities: list[dict]) -> dict:
    """nippo API の一括 upsert を呼ぶ。通信失敗時は urllib の例外をそのまま送出する。"""
    request = urllib.request.Request(
        f"{api.rstrip('/')}/api/activities/bulk",
        data=json.dumps(activities).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as res:
        return json.load(res)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=dt.date.fromisoformat, default=dt.datetime.now(JST).date())
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    parser.add_argument("--dry-run", action="store_true", help="送信せず内容を表示する")
    args = parser.parse_args(argv)

    activities = [to_activity(s, args.date) for s in collect(args.date, args.projects_dir)]
    if args.dry_run:
        print(json.dumps(activities, ensure_ascii=False, indent=2))
        return 0
    if not activities:
        print(f"{args.date} の Claude Code セッションはありません")
        return 0
    try:
        result = post(args.api, activities)
    except urllib.error.URLError as e:
        print(f"エラー: API({args.api})に送信できません: {e}", file=sys.stderr)
        return 1
    print(f"{args.date}: 新規 {result['created']} 件 / 更新 {result['updated']} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
