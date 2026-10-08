"""calendar_connector のテスト。実行: uv run --with pytest --with truststore pytest importer"""

import datetime as dt

import pytest

from calendar_connector import parse_events

DAY = dt.date(2026, 10, 7)


def test_parses_array_inside_extra_text() -> None:
    output = """以下が予定です。
```json
[{"id": "e1", "title": "朝会", "start": "2026-10-07T09:30:00+09:00", "end": "2026-10-07T09:45:00+09:00"}]
```"""
    [event] = parse_events(output, DAY)
    assert event["title"] == "朝会"
    assert event["category"] == "meeting"
    assert event["source"] == "calendar"
    assert event["external_id"] == "gcal:e1"


def test_empty_array() -> None:
    assert parse_events("[]", DAY) == []


def test_skips_broken_and_other_day_events_and_assumes_jst() -> None:
    output = """[
      {"id": "ok", "title": "設計レビュー", "start": "2026-10-07T15:00:00"},
      {"id": "broken", "title": "開始なし"},
      {"id": "other", "title": "翌日", "start": "2026-10-08T10:00:00+09:00"},
      {"id": "utc", "title": "UTCで前日", "start": "2026-10-06T16:00:00Z"}
    ]"""
    titles = [e["title"] for e in parse_events(output, DAY)]
    assert titles == ["設計レビュー", "UTCで前日"]
    assert parse_events(output, DAY)[0]["started_at"] == "2026-10-07T15:00:00+09:00"


def test_rejects_output_without_json() -> None:
    with pytest.raises(RuntimeError, match="JSON"):
        parse_events("カレンダーにアクセスできませんでした", DAY)
