import datetime as dt
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.services.ics_parser import IcsParseError, parse_events

DAY = dt.date(2026, 10, 7)

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:standup
DTSTART:20261001T003000Z
DTEND:20261001T004500Z
RRULE:FREQ=DAILY
SUMMARY:朝会
END:VEVENT
BEGIN:VEVENT
UID:review
DTSTART;TZID=Asia/Tokyo:20261007T150000
DTEND;TZID=Asia/Tokyo:20261007T160000
SUMMARY:設計レビュー
END:VEVENT
BEGIN:VEVENT
UID:allday
DTSTART;VALUE=DATE:20261007
DTEND;VALUE=DATE:20261008
SUMMARY:有給(終日)
END:VEVENT
BEGIN:VEVENT
UID:cancelled
DTSTART:20261007T020000Z
DTEND:20261007T030000Z
STATUS:CANCELLED
SUMMARY:中止になった会議
END:VEVENT
BEGIN:VEVENT
UID:other-day
DTSTART:20261008T020000Z
DTEND:20261008T030000Z
SUMMARY:翌日の会議
END:VEVENT
BEGIN:VEVENT
UID:utc-boundary
DTSTART:20261006T160000Z
DTEND:20261006T170000Z
SUMMARY:JSTでは7日1時
END:VEVENT
END:VCALENDAR
""".encode()


def test_parse_events_filters_and_expands() -> None:
    events = parse_events(ICS, DAY)
    assert [e.title for e in events] == ["JSTでは7日1時", "朝会", "設計レビュー"]
    standup = events[1]
    assert standup.category == "meeting"
    assert standup.source == "calendar"
    assert standup.started_at.isoformat() == "2026-10-07T09:30:00+09:00"
    # 繰り返し予定は日ごとに別の external_id になる
    assert standup.external_id != parse_events(ICS, DAY + dt.timedelta(days=1))[0].external_id


def test_parse_events_rejects_garbage() -> None:
    with pytest.raises(IcsParseError):
        parse_events(b"not an ics", DAY)


def test_import_endpoint_is_idempotent(client: TestClient) -> None:
    files = {"file": ("cal.ics", ICS, "text/calendar")}
    res = client.post("/api/imports/ics", params={"date": DAY.isoformat()}, files=files)
    assert res.json() == {"imported": 3}
    client.post("/api/imports/ics", params={"date": DAY.isoformat()}, files=files)
    assert len(client.get("/api/activities", params={"date": DAY.isoformat()}).json()) == 3


def test_import_endpoint_returns_400_for_garbage(client: TestClient) -> None:
    files = {"file": ("cal.ics", b"garbage", "text/calendar")}
    res = client.post("/api/imports/ics", params={"date": DAY.isoformat()}, files=files)
    assert res.status_code == 400


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


HOLIDAY_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:holiday
DTSTART:20261007T000000Z
DTEND:20261007T010000Z
SUMMARY:祝日カレンダーの予定
END:VEVENT
END:VCALENDAR
""".encode()


def test_parse_google_export_zip_skips_group_calendars() -> None:
    data = _zip(
        {
            "me@example.com.ics": ICS,
            "ja.japanese#holiday@group.v.calendar.google.com.ics": HOLIDAY_ICS,
        }
    )
    titles = [e.title for e in parse_events(data, DAY)]
    assert titles == ["JSTでは7日1時", "朝会", "設計レビュー"]


def test_zip_without_ics_is_rejected() -> None:
    with pytest.raises(IcsParseError):
        parse_events(_zip({"readme.txt": b"x"}), DAY)
