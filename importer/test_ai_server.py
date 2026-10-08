"""ai_server のテスト。実行: uv run --with pytest --with truststore pytest importer"""

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import pytest

import ai_server
import nippo_auto


@pytest.fixture
def base_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setattr(nippo_auto, "load_config", lambda path: {})
    monkeypatch.setattr(nippo_auto, "generate_report", lambda day, config: f"作成:{day}")
    monkeypatch.setattr(nippo_auto, "shorten_report", lambda body, config: f"短縮:{body}")
    server = ThreadingHTTPServer(("127.0.0.1", 0), ai_server.AiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _post(url: str, data: object, headers: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-Nippo-Client": "web"} | (headers or {}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_generate_and_shorten(base_url: str) -> None:
    assert _post(f"{base_url}/ai/generate", {"date": "2026-10-07"}) == (
        200,
        {"body": "作成:2026-10-07"},
    )
    assert _post(f"{base_url}/ai/shorten", {"body": "本文"}) == (200, {"body": "短縮:本文"})


def test_rejects_requests_without_client_header(base_url: str) -> None:
    status, _ = _post(f"{base_url}/ai/shorten", {"body": "本文"}, {"X-Nippo-Client": ""})
    assert status == 403


def test_rejects_foreign_host(base_url: str) -> None:
    status, _ = _post(f"{base_url}/ai/shorten", {"body": "本文"}, {"Host": "evil.example.com"})
    assert status == 403


def test_validates_input(base_url: str) -> None:
    assert _post(f"{base_url}/ai/generate", {"date": "昨日"})[0] == 400
    assert _post(f"{base_url}/ai/shorten", {"body": "  "})[0] == 400
    assert _post(f"{base_url}/ai/unknown", {})[0] == 404
    assert _post(f"{base_url}/ai/shorten", ["配列"])[0] == 400  # type: ignore[arg-type]


def test_unexpected_error_returns_json_500(base_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(body, config):
        raise PermissionError("実行権限がありません")

    monkeypatch.setattr(nippo_auto, "shorten_report", boom)
    status, data = _post(f"{base_url}/ai/shorten", {"body": "本文"})
    assert status == 500
    assert "実行権限がありません" in data["detail"]


def test_reports_ai_failure_with_unsaved_body(
    base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(day, config):
        raise nippo_auto.NippoError("保存できません", unsaved_body="生成済みの本文")

    monkeypatch.setattr(nippo_auto, "generate_report", fail)
    status, data = _post(f"{base_url}/ai/generate", {"date": "2026-10-07"})
    assert status == 502
    assert data["unsaved_body"] == "生成済みの本文"
