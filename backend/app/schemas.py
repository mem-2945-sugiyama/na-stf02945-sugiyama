"""API の入出力スキーマ。"""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Category, Source


class ActivityCreate(BaseModel):
    """画面からの手入力。started_at はサーバー側で現在時刻を入れる。"""

    date: dt.date
    category: Category
    title: str = Field(min_length=1, max_length=500)
    project: str | None = Field(default=None, max_length=200)
    detail: str | None = None


class ActivityUpdate(BaseModel):
    """部分更新。送られた項目だけを更新する。"""

    category: Category | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    project: str | None = Field(default=None, max_length=200)
    detail: str | None = None

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> "ActivityUpdate":
        # 省略(更新しない)と明示的な null(DB の NOT NULL 違反になる)を区別するため
        for name in ("category", "title"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} に null は指定できません")
        return self


class ActivityImport(BaseModel):
    """取り込み(Claude ログ・カレンダー)用。(source, external_id) で upsert する。"""

    date: dt.date
    category: Category
    title: str = Field(min_length=1, max_length=500)
    project: str | None = Field(default=None, max_length=200)
    detail: str | None = None
    started_at: dt.datetime
    ended_at: dt.datetime | None = None
    source: Source
    external_id: str = Field(min_length=1, max_length=200)

    @field_validator("source")
    @classmethod
    def _reject_manual(cls, value: Source) -> Source:
        if value == Source.MANUAL:
            raise ValueError("取り込みで source=manual は指定できません")
        return value


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    started_at: dt.datetime
    ended_at: dt.datetime | None
    category: Category
    project: str | None
    title: str
    detail: str | None
    source: Source
    external_id: str | None
    created_at: dt.datetime


class BulkResult(BaseModel):
    created: int
    updated: int


class ImportResult(BaseModel):
    imported: int


class ReportDraft(BaseModel):
    date: dt.date
    body: str


class ReportWrite(BaseModel):
    """body を省略(null)すると既存の本文を保持する。今日の一言だけを先に保存するため。"""

    body: str | None = None
    comment: str = ""


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: dt.date
    body: str
    comment: str
    updated_at: dt.datetime
