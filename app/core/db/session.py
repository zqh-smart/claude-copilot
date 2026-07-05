from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import PersistenceBackendError


@lru_cache
def get_postgres_engine():
    resolved = get_settings()
    if not resolved.postgres_dsn:
        raise PersistenceBackendError("STORAGE_BACKEND=postgres requires POSTGRES_DSN to be set.")

    try:
        engine = create_engine(resolved.postgres_dsn, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return engine
    except Exception as exc:  # pragma: no cover - depends on environment
        raise PersistenceBackendError(
            f"Failed to initialize PostgreSQL engine from POSTGRES_DSN: {exc}"
        ) from exc


@lru_cache
def get_postgres_session_factory():
    engine = get_postgres_engine()
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False, future=True)
