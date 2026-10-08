"""日報の下書き生成と保存。"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Activity, Report
from app.schemas import ReportDraft, ReportRead, ReportWrite
from app.services.report_builder import build_report

router = APIRouter(prefix="/reports", tags=["reports"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/{date}/draft", response_model=ReportDraft)
def draft_report(date: dt.date, session: SessionDep, comment: str = "") -> ReportDraft:
    stmt = select(Activity).where(Activity.date == date).order_by(Activity.started_at, Activity.id)
    return ReportDraft(date=date, body=build_report(list(session.scalars(stmt)), comment))


@router.get("/{date}", response_model=ReportRead)
def get_report(date: dt.date, session: SessionDep) -> Report:
    report = session.scalar(select(Report).where(Report.date == date))
    if report is None:
        raise HTTPException(status_code=404, detail="日報は未保存です")
    return report


@router.put("/{date}", response_model=ReportRead)
def save_report(date: dt.date, payload: ReportWrite, session: SessionDep) -> Report:
    report = session.scalar(select(Report).where(Report.date == date))
    if report is None:
        report = Report(date=date, body="")
        session.add(report)
    if payload.body is not None:
        report.body = payload.body
    report.comment = payload.comment
    session.commit()
    session.refresh(report)
    return report
