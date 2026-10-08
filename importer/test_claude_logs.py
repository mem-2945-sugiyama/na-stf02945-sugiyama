"""claude_logs のテスト。実行: uv run --with pytest --with truststore pytest importer"""

import datetime as dt
import json
import os
from pathlib import Path

from claude_logs import collect, to_activity

DAY = dt.date(2026, 10, 7)


def _user(text_or_blocks, ts: str, sid: str = "s1", **extra) -> dict:
    return {
        "type": "user",
        "sessionId": sid,
        "timestamp": ts,
        "cwd": "/Users/me/work/nippo",
        "message": {"role": "user", "content": text_or_blocks},
        **extra,
    }


def _edit(path: str, ts: str, sid: str = "s1") -> dict:
    return {
        "type": "assistant",
        "sessionId": sid,
        "timestamp": ts,
        "cwd": "/Users/me/work/nippo",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": path}}],
        },
    }


def _write_log(tmp_path: Path, records: list, name: str = "s1.jsonl") -> Path:
    project = tmp_path / "-Users-me-work-nippo"
    project.mkdir(exist_ok=True)
    path = project / name
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_collects_only_the_day_in_jst(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        [
            _user("前日の依頼", "2026-10-06T14:59:59Z"),  # JST 10/6 23:59
            _user("当日の依頼", "2026-10-06T15:00:00Z"),  # JST 10/7 0:00
            _user("翌日の依頼", "2026-10-07T15:00:00Z"),  # JST 10/8 0:00
        ],
    )
    [session] = collect(DAY, tmp_path)
    assert session.prompts == ["当日の依頼"]


def test_excludes_meta_tool_results_tags_and_noise(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        [
            _user("メタ情報", "2026-10-07T01:00:00Z", isMeta=True),
            _user([{"type": "tool_result", "content": "結果"}], "2026-10-07T01:01:00Z"),
            _user("<command-name>/clear</command-name>", "2026-10-07T01:02:00Z"),
            _user("[Request interrupted by user]", "2026-10-07T01:03:00Z"),
            _user(
                [
                    {"type": "text", "text": "<system-reminder>\n内部\n</system-reminder>"},
                    {"type": "text", "text": "日報アプリを\n作りたい"},
                ],
                "2026-10-07T01:04:00Z",
            ),
            _user("サブエージェント", "2026-10-07T01:05:00Z", isSidechain=True),
        ],
    )
    [session] = collect(DAY, tmp_path)
    assert session.prompts == ["日報アプリを 作りたい"]


def test_skips_broken_lines_and_builds_activity(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        [
            "{壊れた行",
            _user("API を作って", "2026-10-07T01:00:00Z"),
            _edit("/Users/me/work/nippo/backend/app/main.py", "2026-10-07T01:10:00Z"),
            _edit("/Users/me/work/nippo/backend/app/main.py", "2026-10-07T01:20:00Z"),
            _edit("/tmp/other.txt", "2026-10-07T01:30:00Z"),
            {"type": "ai-title", "sessionId": "s1", "aiTitle": "日報 API の実装"},
        ],
    )
    [session] = collect(DAY, tmp_path)
    activity = to_activity(session, DAY)

    assert activity["title"] == "日報 API の実装(変更 2 ファイル)"
    assert activity["project"] == "nippo"
    assert activity["source"] == "claude"
    assert activity["external_id"] == "s1@2026-10-07"
    assert activity["started_at"] == "2026-10-07T10:00:00+09:00"
    assert activity["ended_at"] == "2026-10-07T10:30:00+09:00"
    assert "- backend/app/main.py" in activity["detail"]
    assert "- /tmp/other.txt" in activity["detail"]


def test_keeps_only_substantial_answers(tmp_path: Path) -> None:
    def answer(text: str, ts: str) -> dict:
        return {
            "type": "assistant",
            "sessionId": "s1",
            "timestamp": ts,
            "cwd": "/Users/me/work/nippo",
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
        }

    long_answer = "FastAPI では def のエンドポイントがスレッドプールで実行されます。" * 3
    _write_log(
        tmp_path,
        [
            _user("教えて", "2026-10-07T01:00:00Z"),
            answer("確認します。", "2026-10-07T01:01:00Z"),
            answer(long_answer, "2026-10-07T01:02:00Z"),
        ],
    )
    [session] = collect(DAY, tmp_path)
    assert session.answers == [long_answer]
    assert "Claude の回答(抜粋):" in to_activity(session, DAY)["detail"]


def test_title_falls_back_to_first_prompt(tmp_path: Path) -> None:
    _write_log(tmp_path, [_user("あ" * 100, "2026-10-07T01:00:00Z")])
    [session] = collect(DAY, tmp_path)
    title = to_activity(session, DAY)["title"]
    assert len(title) == 60 and title.endswith("…")


def test_skips_files_not_updated_since_the_day(tmp_path: Path) -> None:
    path = _write_log(tmp_path, [_user("古いが中身は当日", "2026-10-07T01:00:00Z")])
    old = dt.datetime(2026, 10, 6, 12, tzinfo=dt.UTC).timestamp()
    os.utime(path, (old, old))
    assert collect(DAY, tmp_path) == []


def test_ignores_subagent_logs(tmp_path: Path) -> None:
    _write_log(tmp_path, [_user("親", "2026-10-07T01:00:00Z")])
    sub = tmp_path / "-Users-me-work-nippo" / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-x.jsonl").write_text(
        json.dumps(_user("子", "2026-10-07T01:00:00Z", sid="s2"), ensure_ascii=False) + "\n"
    )
    assert [s.session_id for s in collect(DAY, tmp_path)] == ["s1"]


def test_sample_evenly_keeps_first_and_last() -> None:
    from claude_logs import sample_evenly

    items = [str(i) for i in range(25)]
    picked = sample_evenly(items, 10)
    assert len(picked) == 10 and picked[0] == "0" and picked[-1] == "24"
    assert sample_evenly(items[:3], 10) == items[:3]
    assert sample_evenly(items, 1) == ["0"]
    assert sample_evenly(items, 0) == []


def test_longest_in_order_keeps_chronology() -> None:
    from claude_logs import longest_in_order

    assert longest_in_order(["aaa", "b", "cccc", "dd"], 2) == ["aaa", "cccc"]
