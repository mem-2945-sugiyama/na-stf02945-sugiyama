"""活動の取り込み(upsert)。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity
from app.schemas import ActivityImport, BulkResult

# 再取り込みで上書きする項目。category は含めない:
# 取り込み後にユーザーが画面で付け替えた分類(例: 作業 → 技術の学び)を消さないため
_IMPORT_OWNED_FIELDS = ("date", "title", "project", "detail", "started_at", "ended_at")


def upsert_activities(session: Session, items: list[ActivityImport]) -> BulkResult:
    """(source, external_id) が一致すれば更新、なければ追加する。

    session をコミットする。同じリスト内に同じキーが複数あれば後勝ち。
    """
    created = updated = 0
    for item in items:
        existing = session.scalar(
            select(Activity).where(
                Activity.source == item.source, Activity.external_id == item.external_id
            )
        )
        if existing is None:
            session.add(Activity(**item.model_dump()))
            # 同じリスト内の重複キーを次の select で見つけられるよう即時反映する
            session.flush()
            created += 1
        else:
            for name in _IMPORT_OWNED_FIELDS:
                setattr(existing, name, getattr(item, name))
            updated += 1
    session.commit()
    return BulkResult(created=created, updated=updated)
