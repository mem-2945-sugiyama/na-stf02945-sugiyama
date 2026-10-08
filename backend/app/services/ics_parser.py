"""カレンダーの .ics から指定日の予定を取り出す。

Google Calendar API の OAuth 設定を避けるための代替手段。
"""

import datetime as dt
import io
import zipfile
from zoneinfo import ZoneInfo

import recurring_ical_events
from icalendar import Calendar

from app.models import Category, Source
from app.schemas import ActivityImport

JST = ZoneInfo("Asia/Tokyo")
# 祝日カレンダーや共有のグループカレンダーは自分の予定ではないため、zip から取り込まない
_GROUP_CALENDAR_MARKERS = ("group.calendar.google.com", "group.v.calendar.google.com")
# zip 爆弾(展開すると巨大になるファイル)対策の展開後サイズ上限
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024


class IcsParseError(ValueError):
    """.ics として解釈できないデータを受け取ったときに送出する。"""


def parse_events(data: bytes, day: dt.date) -> list[ActivityImport]:
    """day(JST)に開始する予定を、会議カテゴリの取り込みデータにして返す。

    data は .ics か、Google カレンダーのエクスポート(.ics を束ねた zip)。
    zip の場合、祝日・グループカレンダーを除いた全カレンダーの .ics を対象にする。
    他の人の個人カレンダーを「マイカレンダー」に追加していると、その予定も取り込まれる。
    終日予定とキャンセル済みの予定は除外する。
    不正なデータには IcsParseError を送出する。
    """
    if not zipfile.is_zipfile(io.BytesIO(data)):
        return _parse_ics(data, day)
    results: list[ActivityImport] = []
    for ics in _extract_non_group_calendars(data):
        results.extend(_parse_ics(ics, day))
    return sorted(results, key=lambda a: a.started_at)


def _extract_non_group_calendars(data: bytes) -> list[bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [
                m
                for m in archive.infolist()
                if m.filename.lower().endswith(".ics")
                and not any(marker in m.filename for marker in _GROUP_CALENDAR_MARKERS)
            ]
            if sum(m.file_size for m in members) > MAX_EXTRACTED_BYTES:
                raise IcsParseError("zip の展開後のサイズが大きすぎます")
            if not members:
                raise IcsParseError("zip の中に取り込める .ics がありません")
            return [archive.read(m) for m in members]
    except zipfile.BadZipFile as e:
        raise IcsParseError(f"zip を展開できません: {e}") from e


def _parse_ics(data: bytes, day: dt.date) -> list[ActivityImport]:
    try:
        calendar = Calendar.from_ical(data)
        # at(day) は日付を floating time(タイムゾーンなし)で解釈し、UTC 表記の予定が
        # JST の日付境界からずれるため、JST の 0:00〜翌 0:00 を明示して取る
        day_start = dt.datetime.combine(day, dt.time(), tzinfo=JST)
        events = recurring_ical_events.of(calendar).between(
            day_start, day_start + dt.timedelta(days=1)
        )
    except Exception as e:  # icalendar は不正入力に対し様々な例外を出すため一括で扱う
        raise IcsParseError(f".ics を解釈できません: {e}") from e

    results: list[ActivityImport] = []
    for event in events:
        start_prop = event.get("DTSTART")
        if start_prop is None:
            continue
        start = start_prop.dt
        # 終日予定は休暇やリマインダーが多く、作業実績として載せると日報が汚れるため除外
        if not isinstance(start, dt.datetime):
            continue
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        start = _to_jst(start)
        # between はその日に重なる予定(前日から続く予定など)も返すため、開始日で絞る
        if start.date() != day:
            continue
        end_prop = event.get("DTEND")
        end = _to_jst(end_prop.dt) if end_prop and isinstance(end_prop.dt, dt.datetime) else None
        uid = str(event.get("UID", "")) or f"no-uid:{event.get('SUMMARY', '')}"
        results.append(
            ActivityImport(
                date=day,
                category=Category.MEETING,
                title=(str(event.get("SUMMARY", "")).strip() or "(無題の予定)")[:500],
                started_at=start,
                ended_at=end,
                source=Source.CALENDAR,
                # 繰り返し予定の各回は UID を共有するため、開始時刻と組み合わせて一意にする。
                # 長さ制限は UID 側で切る(末尾の開始時刻が消えると各回が同じ ID になるため)
                external_id=f"{uid[:160]}@{start.isoformat()}",
            )
        )
    return sorted(results, key=lambda a: a.started_at)


def _to_jst(value: dt.datetime) -> dt.datetime:
    # タイムゾーンなし(floating time)の予定は日本時間とみなす
    if value.tzinfo is None:
        return value.replace(tzinfo=JST)
    return value.astimezone(JST)
