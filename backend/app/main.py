"""nippo API のエントリポイント。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app import models  # noqa: F401  create_all の前にテーブル定義を登録するため
from app.db import Base, engine
from app.routers import activities, imports, reports


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # マイグレーションツールが未導入のため、起動時に未作成のテーブルだけを作る。
    # 既存テーブルの変更は反映されないので、スキーマを変えるときは Alembic 等を導入する
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="nippo", lifespan=lifespan)

# すべて /api 配下に置く。本番は CloudFront で /api/* だけを ECS に振り分け、
# それ以外を S3 の画面に流すため
api = APIRouter(prefix="/api")
api.include_router(activities.router)
api.include_router(imports.router)
api.include_router(reports.router)


@api.get("/health")
def health() -> dict[str, str]:
    """ECS / ALB のヘルスチェック用。DB には触らない。"""
    return {"status": "ok"}


app.include_router(api)
