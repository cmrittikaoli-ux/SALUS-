from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from . import config

engine = create_engine(
    config.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"options": f"-c timezone={config.TIMEZONE}"},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- raw-SQL helpers (used for the ranking / overlap / window queries) ---

def fetch_all(db: Session, sql: str, **params: Any) -> list[dict]:
    return [dict(r) for r in db.execute(text(sql), params).mappings().all()]


def fetch_one(db: Session, sql: str, **params: Any) -> dict | None:
    row = db.execute(text(sql), params).mappings().first()
    return dict(row) if row else None
