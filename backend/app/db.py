"""DB 接続とセッション管理。"""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# 接続先は環境変数で差し替える(ローカルは docker compose の Postgres、本番は RDS)
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://nippo:nippo@localhost:5432/nippo"
)

# pool_pre_ping: RDS 側でアイドル接続が切られても、次のリクエストでエラーにしないため
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    """リクエスト単位の DB セッションを返す FastAPI 依存関数。

    コミットは呼び出し側(各エンドポイント)の責務。
    """
    with SessionLocal() as session:
        yield session
