"""外部データの取り込み(.ics)。"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import ImportResult
from app.services.activity_store import upsert_activities
from app.services.ics_parser import IcsParseError, parse_events

router = APIRouter(prefix="/imports", tags=["imports"])
SessionDep = Annotated[Session, Depends(get_session)]

# Google カレンダーの書き出しは数年分で数 MB になることがあるため、余裕を持たせた上限
MAX_ICS_BYTES = 20 * 1024 * 1024


# def(同期)にする: 解析と DB 書き込みが同期処理のため、async def だとイベントループを止めてしまう。
# def なら FastAPI がスレッドプールで実行する
@router.post("/ics", response_model=ImportResult)
def import_ics(date: dt.date, file: UploadFile, session: SessionDep) -> ImportResult:
    data = file.file.read(MAX_ICS_BYTES + 1)
    if len(data) > MAX_ICS_BYTES:
        raise HTTPException(status_code=413, detail=".ics ファイルが大きすぎます")
    try:
        items = parse_events(data, date)
    except IcsParseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    result = upsert_activities(session, items)
    return ImportResult(imported=result.created + result.updated)
