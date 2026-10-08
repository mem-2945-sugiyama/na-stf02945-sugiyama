"""活動の登録・一覧・編集・削除と、取り込み用の一括 upsert。"""

import datetime as dt
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Activity, Source
from app.schemas import ActivityCreate, ActivityImport, ActivityRead, ActivityUpdate, BulkResult
from app.services.activity_store import upsert_activities

JST = ZoneInfo("Asia/Tokyo")

router = APIRouter(prefix="/activities", tags=["activities"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[ActivityRead])
def list_activities(date: dt.date, session: SessionDep) -> list[Activity]:
    stmt = select(Activity).where(Activity.date == date).order_by(Activity.started_at, Activity.id)
    return list(session.scalars(stmt))


@router.post("", response_model=ActivityRead, status_code=201)
def create_activity(payload: ActivityCreate, session: SessionDep) -> Activity:
    activity = Activity(
        **payload.model_dump(), source=Source.MANUAL, started_at=dt.datetime.now(JST)
    )
    session.add(activity)
    session.commit()
    session.refresh(activity)
    return activity


@router.post("/bulk", response_model=BulkResult)
def bulk_upsert(items: list[ActivityImport], session: SessionDep) -> BulkResult:
    return upsert_activities(session, items)


@router.patch("/{activity_id}", response_model=ActivityRead)
def update_activity(activity_id: int, payload: ActivityUpdate, session: SessionDep) -> Activity:
    activity = _get_or_404(session, activity_id)
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(activity, name, value)
    session.commit()
    session.refresh(activity)
    return activity


@router.delete("/{activity_id}", status_code=204)
def delete_activity(activity_id: int, session: SessionDep) -> Response:
    session.delete(_get_or_404(session, activity_id))
    session.commit()
    return Response(status_code=204)


def _get_or_404(session: Session, activity_id: int) -> Activity:
    activity = session.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="活動が見つかりません")
    return activity
