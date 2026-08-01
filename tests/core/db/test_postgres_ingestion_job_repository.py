import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from app.core.db.postgres_ingestion_job_repository import (
    PostgresIngestionJobRepository,
)
from app.core.db.postgres_models import DocumentORM, IngestionJobORM
from src.claude_copilot.schemas.ingestion import IngestionJob

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1",
    reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
)


def test_postgres_claim_is_atomic_and_expired_lease_is_reclaimable() -> None:
    dsn = os.getenv(
        "POSTGRES_DSN",
        "postgresql+psycopg://postgres:postgres@localhost:5432/claude_copilot",
    )
    engine = create_engine(dsn)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    repository = PostgresIngestionJobRepository(session_factory)
    now = datetime.now(UTC)
    suffix = uuid4().hex
    doc_id = f"lease-doc-{suffix}"
    job_id = f"lease-job-{suffix}"

    with session_factory() as session:
        session.add(
            DocumentORM(
                doc_id=doc_id,
                filename="lease-test.pdf",
                status="waiting",
                created_at=now,
                updated_at=now,
                storage_path="tests/lease-test.pdf",
                metadata_json={},
            )
        )
        session.commit()
    repository.save(
        IngestionJob(
            job_id=job_id,
            doc_id=doc_id,
            filename="lease-test.pdf",
            created_at=now,
            updated_at=now,
        )
    )

    def claim(worker_id: str):
        return repository.claim(
            job_id,
            worker_id=worker_id,
            now=now,
            lease_expires_at=now + timedelta(seconds=30),
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, ["worker-a", "worker-b"]))
        winner = next(job for job in results if job is not None)
        assert sum(job is not None for job in results) == 1
        assert winner.attempt == 1

        stored = repository.get(job_id)
        stored.lease_expires_at = now - timedelta(seconds=1)
        repository.save_owned(stored, worker_id=stored.worker_id or "")
        reclaimed = repository.claim(
            job_id,
            worker_id="worker-c",
            now=now,
            lease_expires_at=now + timedelta(seconds=30),
        )
        assert reclaimed is not None
        assert reclaimed.worker_id == "worker-c"
        assert reclaimed.attempt == 2

        requested = repository.request_cancel(
            job_id,
            now=now + timedelta(seconds=1),
        )
        assert requested is not None
        assert requested.cancel_requested_at is not None
        reclaimed.progress_percent = 50
        saved = repository.save_owned(reclaimed, worker_id="worker-c")
        assert saved is not None
        assert saved.cancel_requested_at == requested.cancel_requested_at
    finally:
        with session_factory() as session:
            session.execute(delete(IngestionJobORM).where(IngestionJobORM.job_id == job_id))
            session.execute(delete(DocumentORM).where(DocumentORM.doc_id == doc_id))
            session.commit()
        engine.dispose()
