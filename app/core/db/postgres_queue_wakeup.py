from __future__ import annotations

from collections.abc import Generator

import psycopg

INGESTION_QUEUE_CHANNEL = "ingestion_jobs_ready"


def psycopg_dsn(sqlalchemy_dsn: str) -> str:
    return sqlalchemy_dsn.replace("postgresql+psycopg://", "postgresql://", 1)


class PostgresIngestionQueueWakeup:
    """Wait for durable queue notifications while retaining a timeout fallback."""

    def __init__(self, dsn: str) -> None:
        self._connection = psycopg.connect(psycopg_dsn(dsn), autocommit=True)
        self._connection.execute(f"LISTEN {INGESTION_QUEUE_CHANNEL}")

    def wait(self, timeout_seconds: float) -> bool:
        notifications: Generator[psycopg.Notify, None, None] = self._connection.notifies(
            timeout=max(0.05, timeout_seconds),
            stop_after=1,
        )
        return next(notifications, None) is not None

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> PostgresIngestionQueueWakeup:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
