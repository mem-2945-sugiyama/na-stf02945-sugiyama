"""DB モデル。"""

import datetime as dt
from enum import StrEnum

from sqlalchemy import Date, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Category(StrEnum):
    """活動の種類。日報のどのセクションに載るかを決める。"""

    WORK = "work"
    MEETING = "meeting"
    TECH_LEARNING = "tech_learning"
    BUSINESS_LEARNING = "business_learning"


class Source(StrEnum):
    """活動の登録元。"""

    MANUAL = "manual"
    CLAUDE = "claude"
    CALENDAR = "calendar"
    SLACK = "slack"


class Activity(Base):
    __tablename__ = "activities"
    # 取り込みを何度実行しても重複しないよう、取り込み元ごとの外部 ID で一意にする。
    # 手入力は external_id が NULL で、NULL 同士は一意制約に掛からない
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_activities_source_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # 列挙値の追加でマイグレーションが要らないよう、DB の ENUM 型ではなく文字列で持つ
    category: Mapped[str] = mapped_column(String(32))
    project: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(500))
    detail: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, unique=True)
    body: Mapped[str] = mapped_column(Text)
    comment: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
