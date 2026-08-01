from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db.postgres_mappers import ingestion_job_from_orm, ingestion_job_to_orm
from app.core.db.postgres_models import IngestionJobORM
from app.core.errors import IngestionJobNotFoundError
from src.claude_copilot.schemas.ingestion import (
    IngestionJob,
    IngestionJobEvent,
    IngestionJobStatus,
)


class PostgresIngestionJobRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list(self, *, limit: int = 100) -> list[IngestionJob]:
        with self._session_factory() as session:
            rows = session.execute(
                select(IngestionJobORM)
                .order_by(IngestionJobORM.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return [ingestion_job_from_orm(row) for row in rows]

    def get(self, job_id: str) -> IngestionJob:
        with self._session_factory() as session:
            row = session.get(IngestionJobORM, job_id)
            if row is None:
                raise IngestionJobNotFoundError(f"Ingestion job not found: {job_id}")
            return ingestion_job_from_orm(row)

    def save(self, job: IngestionJob) -> IngestionJob:
        with self._session_factory() as session:
            session.merge(ingestion_job_to_orm(job))
            session.commit()
        return job

    def claim(
        self,
        job_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> IngestionJob | None:
        with self._session_factory() as session:
            row = session.execute(
                select(IngestionJobORM)
                .where(IngestionJobORM.job_id == job_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                raise IngestionJobNotFoundError(f"Ingestion job not found: {job_id}")
            reclaimable = (
                row.status == IngestionJobStatus.RUNNING.value
                and row.lease_expires_at is not None
                and row.lease_expires_at <= now
            )
            retry_ready = (
                row.status == IngestionJobStatus.RETRY_WAIT.value
                and (row.available_at is None or row.available_at <= now)
            )
            if (
                row.status != IngestionJobStatus.QUEUED.value
                and not reclaimable
                and not retry_ready
            ):
                return None
            row.status = IngestionJobStatus.RUNNING.value
            row.worker_id = worker_id
            row.heartbeat_at = now
            row.lease_expires_at = lease_expires_at
            row.available_at = None
            row.started_at = row.started_at or now
            row.updated_at = now
            row.attempt += 1
            session.commit()
            session.refresh(row)
            return ingestion_job_from_orm(row)

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> bool:
        with self._session_factory() as session:
            row = session.execute(
                select(IngestionJobORM)
                .where(IngestionJobORM.job_id == job_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                raise IngestionJobNotFoundError(f"Ingestion job not found: {job_id}")
            if (
                row.status != IngestionJobStatus.RUNNING.value
                or row.worker_id != worker_id
                or row.lease_expires_at is None
                or row.lease_expires_at <= now
            ):
                return False
            row.heartbeat_at = now
            row.lease_expires_at = lease_expires_at
            row.updated_at = now
            session.commit()
            return True

    def save_owned(self, job: IngestionJob, *, worker_id: str) -> IngestionJob | None:
        with self._session_factory() as session:
            row = session.execute(
                select(IngestionJobORM)
                .where(IngestionJobORM.job_id == job.job_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                raise IngestionJobNotFoundError(
                    f"Ingestion job not found: {job.job_id}"
                )
            if row.worker_id != worker_id:
                return None
            if row.cancel_requested_at is not None:
                job.cancel_requested_at = row.cancel_requested_at
            replacement = ingestion_job_to_orm(job)
            for column in IngestionJobORM.__table__.columns:
                if column.name == "job_id":
                    continue
                setattr(row, column.name, getattr(replacement, column.name))
            session.commit()
            session.refresh(row)
            return ingestion_job_from_orm(row)

    def request_cancel(self, job_id: str, *, now: datetime) -> IngestionJob | None:
        with self._session_factory() as session:
            row = session.execute(
                select(IngestionJobORM)
                .where(IngestionJobORM.job_id == job_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                raise IngestionJobNotFoundError(f"Ingestion job not found: {job_id}")
            if row.status != IngestionJobStatus.RUNNING.value:
                return None
            row.cancel_requested_at = now
            row.updated_at = now
            events = list(row.events or [])
            events.append(
                IngestionJobEvent(
                    timestamp=now,
                    status=IngestionJobStatus.RUNNING,
                    stage=row.stage,
                    progress_percent=row.progress_percent,
                    message="Cancellation requested; waiting for a stage boundary.",
                ).model_dump(mode="json")
            )
            row.events = events
            session.commit()
            session.refresh(row)
            return ingestion_job_from_orm(row)
