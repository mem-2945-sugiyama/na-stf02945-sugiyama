# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "truststore>=0.9",
# ]
# ///
"""画面の「AI で作成」「AI で短く」ボタンから Claude を呼ぶための、Mac 上の小さなサーバー。

API サーバー(Docker や AWS)には Claude Code のログイン情報がないため、Claude を使う処理だけを
この Mac で受け持つ。画面からは Vite の開発サーバー経由(/ai)で呼ばれる。

使い方:
    uv run importer/ai_server.py      # http://127.0.0.1:8001 で待ち受ける

エンドポイント(いずれも POST・JSON。ヘッダー X-Nippo-Client: web が必須):
    /ai/generate  {"date": "YYYY-MM-DD"}  → 材料を集めて日報を作成・保存 → {"body": "..."}
    /ai/shorten   {"body": "..."}         → 本文を短く書き直す(保存しない) → {"body": "..."}
"""

import argparse
import datetime as dt
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import nippo_auto

# 他のサイトから呼ばれないようにするための必須ヘッダー。
# 独自ヘッダー付きのリクエストはブラウザが事前確認(CORS プリフライト)を行い、
# このサーバーは許可を返さないため、別のオリジンのページからは送れない
CLIENT_HEADER = "X-Nippo-Client"
CLIENT_VALUE = "web"
# DNS リバインディング(外部ドメインを 127.0.0.1 に向ける攻撃)を防ぐため、Host を検査する。
# ブラウザが 8001 番を直接叩く場合の対策。Vite 経由(/ai)では changeOrigin で Host が書き換わるため、
# その経路は Vite の allowedHosts(既定で localhost のみ)に頼っている
ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
MAX_BODY_BYTES = 1024 * 1024

# ボタンの連打などで、このサーバー内で Claude を同時に呼ばないようにする(利用枠の無駄と本文の競合を防ぐ)。
# プロセス内のロックなので、launchd などから別に実行した nippo_auto.py とは排他しない。
# そちらと重なった場合は後から保存した方が残る(どちらも同じ材料から作るため実害は小さい)
_ai_lock = threading.Lock()


class BadRequest(ValueError):
    """利用者の入力(リクエスト内容)が不正なことを表す。400 で返す。"""


class AiHandler(BaseHTTPRequestHandler):
    config_path: Path = nippo_auto.CONFIG_PATH

    def do_POST(self) -> None:  # noqa: N802 (http.server の命名規約)
        if not self._is_allowed():
            self._send(403, {"detail": "許可されていないリクエストです"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                raise ValueError
            if length > MAX_BODY_BYTES:
                self._send(413, {"detail": "リクエストが大きすぎます"})
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:  # json.JSONDecodeError も ValueError の一種
            self._send(400, {"detail": "JSON を解釈できません"})
            return

        try:
            if not isinstance(payload, dict):
                raise BadRequest("JSON オブジェクトを送ってください")
            if self.path == "/ai/generate":
                day = self._parse_date(payload)
                self._handle(lambda config: nippo_auto.generate_report(day, config))
            elif self.path == "/ai/shorten":
                body = self._parse_body(payload)
                self._handle(lambda config: nippo_auto.shorten_report(body, config))
            else:
                self._send(404, {"detail": "見つかりません"})
        except BadRequest as e:
            self._send(400, {"detail": str(e)})

    def _is_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return (
            host in ALLOWED_HOSTS
            and self.headers.get(CLIENT_HEADER) == CLIENT_VALUE
            and (self.headers.get("Content-Type") or "").startswith("application/json")
        )

    def _handle(self, action) -> None:
        if not _ai_lock.acquire(blocking=False):
            self._send(
                409, {"detail": "別の AI 処理を実行中です。終わってからもう一度押してください"}
            )
            return
        try:
            self._send(200, {"body": action(nippo_auto.load_config(self.config_path))})
        except nippo_auto.NippoError as e:
            self._send(502, {"detail": str(e), "unsaved_body": e.unsaved_body})
        except Exception as e:
            # 想定外の例外でも必ず JSON で返す。応答なしで切断すると、画面には
            # 「AI サーバーに接続できません」と出て、起動しているのに原因を取り違えるため
            print(f"エラー: {e!r}", file=sys.stderr)
            self._send(500, {"detail": f"AI サーバーで予期しないエラーが発生しました: {e}"})
        finally:
            _ai_lock.release()

    @staticmethod
    def _parse_date(payload: dict) -> dt.date:
        try:
            return dt.date.fromisoformat(str(payload.get("date", "")))
        except ValueError as e:
            raise BadRequest("日付は YYYY-MM-DD 形式で指定してください") from e

    @staticmethod
    def _parse_body(payload: dict) -> str:
        body = payload.get("body")
        if not isinstance(body, str) or not body.strip():
            raise BadRequest("短くする本文がありません")
        return body

    def _send(self, status: int, data: dict) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--config", type=Path, default=nippo_auto.CONFIG_PATH)
    args = parser.parse_args(argv)
    AiHandler.config_path = args.config
    # 127.0.0.1 に限定する: 他の端末から本人の Claude の利用枠を使われないようにするため
    server = ThreadingHTTPServer(("127.0.0.1", args.port), AiHandler)
    print(f"nippo AI サーバー: http://127.0.0.1:{args.port} (Ctrl+C で停止)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
