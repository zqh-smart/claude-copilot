from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import RLock

from app.core.errors import IngestionJobNotFoundError
from src.claude_copilot.schemas.ingestion import (
    IngestionJob,
    IngestionJobEvent,
    IngestionJobStatus,
)


class LocalIngestionJobRepository:
    """Durable, thread-safe local job storage for development and single-host runs."""

    def __init__(self, base_dir: str) -> None:
        self._file_path = Path(base_dir) / "ingestion_jobs.json"
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def list(self, *, limit: int = 100) -> list[IngestionJob]:
        with self._lock:
            jobs = [IngestionJob.model_validate(item) for item in self._read_all().values()]
        jobs.sort(key=lambda item: item.created_at, reverse=True)
        return jobs[:limit]

    def get(self, job_id: str) -> IngestionJob:
        with self._lock:
            item = self._read_all().get(job_id)
        if item is None:
            raise IngestionJobNotFoundError(f"Ingestion job not found: {job_id}")
        return IngestionJob.model_validate(item)

    def save(self, job: IngestionJob) -> IngestionJob:
        with self._lock:
            payload = self._read_all()
            payload[job.job_id] = job.model_dump(mode="json")
            self._write_all(payload)
        return job

    def claim(
        self,
        job_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> IngestionJob | None:
        with self._lock:
            payload = self._read_all()
            item = payload.get(job_id)
            if item is None:
                raise IngestionJobNotFoundError(f"Ingestion job not found: {job_id}")
            job = IngestionJob.model_validate(item)
            reclaimable = (
                job.status == IngestionJobStatus.RUNNING
                and job.lease_expires_at is not None
                and job.lease_expires_at <= now
            )
            retry_ready = (
                job.status == IngestionJobStatus.RETRY_WAIT
                and (job.available_at is None or job.available_at <= now)
            )
            if (
                job.status != IngestionJobStatus.QUEUED
                and not reclaimable
                and not retry_ready
            ):
                return None
            job.status = IngestionJobStatus.RUNNING
            job.worker_id = worker_id
            job.heartbeat_at = now
            job.lease_expires_at = lease_expires_at
            job.available_at = None
            job.started_at = job.started_at or now
            job.updated_at = now
            job.attempt += 1
            payload[job_id] = job.model_dump(mode="json")
            self._write_all(payload)
            return job

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> bool:
        with self._lock:
            payload = self._read_all()
            item = payload.get(job_id)
            if item is None:
                raise IngestionJobNotFoundError(f"Ingestion job not found: {job_id}")
            job = IngestionJob.model_validate(item)
            if (
                job.status != IngestionJobStatus.RUNNING
                or job.worker_id != worker_id
                or job.lease_expires_at is None
                or job.lease_expires_at <= now
            ):
                return False
            job.heartbeat_at = now
            job.lease_expires_at = lease_expires_at
            job.updated_at = now
            payload[job_id] = job.model_dump(mode="json")
            self._write_all(payload)
            return True

    def save_owned(self, job: IngestionJob, *, worker_id: str) -> IngestionJob | None:
        with self._lock:
            payload = self._read_all()
            item = payload.get(job.job_id)
            if item is None:
                raise IngestionJobNotFoundError(
                    f"Ingestion job not found: {job.job_id}"
                )
            stored = IngestionJob.model_validate(item)
            if stored.worker_id != worker_id:
                return None
            if stored.cancel_requested_at is not None:
                job.cancel_requested_at = stored.cancel_requested_at
            payload[job.job_id] = job.model_dump(mode="json")
            self._write_all(payload)
            return job

    def request_cancel(self, job_id: str, *, now: datetime) -> IngestionJob | None:
        with self._lock:
            payload = self._read_all()
            item = payload.get(job_id)
            if item is None:
                raise IngestionJobNotFoundError(f"Ingestion job not found: {job_id}")
            job = IngestionJob.model_validate(item)
            if job.status != IngestionJobStatus.RUNNING:
                return None
            job.cancel_requested_at = now
            job.updated_at = now
            job.events.append(
                IngestionJobEvent(
                    timestamp=now,
                    status=job.status,
                    stage=job.stage,
                    progress_percent=job.progress_percent,
                    message="Cancellation requested; waiting for a stage boundary.",
                )
            )
            payload[job_id] = job.model_dump(mode="json")
            self._write_all(payload)
            return job

    def _read_all(self) -> dict[str, dict]:
        if not self._file_path.exists():
            return {}
        raw = self._file_path.read_text(encoding="utf-8").strip()
        return json.loads(raw) if raw else {}

    def _write_all(self, payload: dict[str, dict]) -> None:
        temporary = self._file_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self._file_path)
