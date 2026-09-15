from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event, RLock, Thread, Timer
from uuid import uuid4

from app.core.db import IngestionJobRepositoryProtocol
from app.core.errors import DocumentProcessingCancelledError
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService
from src.claude_copilot.schemas.document import DocumentProcessingStatus, DocumentRecord
from src.claude_copilot.schemas.ingestion import (
    IngestionJob,
    IngestionJobEvent,
    IngestionJobStatus,
    IngestionQueueAlert,
    IngestionQueueMetrics,
)

_STAGE_PROGRESS = {
    DocumentProcessingStatus.WAITING: 0,
    DocumentProcessingStatus.PARSING: 15,
    DocumentProcessingStatus.CLEANING: 35,
    DocumentProcessingStatus.CHUNKING: 60,
    DocumentProcessingStatus.INDEXING: 80,
    DocumentProcessingStatus.COMPLETED: 100,
    DocumentProcessingStatus.FAILED: 100,
    DocumentProcessingStatus.PAUSED: 0,
}


class IngestionJobService:
    """Persistent ingestion job coordinator with a local background executor.

    Job state is stored independently of worker threads, so queued/running jobs
    can be recovered after an API restart. Pipeline side effects remain keyed by
    document id and are safe to replace during retry.
    """

    def __init__(
        self,
        *,
        pipeline_service: DocumentPipelineService,
        repository: IngestionJobRepositoryProtocol,
        worker_count: int = 2,
        default_max_attempts: int = 3,
        retry_delay_seconds: float = 2.0,
        lease_seconds: float = 120.0,
        heartbeat_seconds: float = 30.0,
        worker_id: str | None = None,
        inline_execution_enabled: bool = True,
        alert_oldest_ready_seconds: float = 300.0,
        alert_retry_wait_count: int = 5,
        alert_recent_failure_count: int = 1,
        alert_failure_window_seconds: float = 3600.0,
    ) -> None:
        self._pipeline = pipeline_service
        self._repository = repository
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, worker_count),
            thread_name_prefix="document-ingestion",
        )
        self._default_max_attempts = max(1, default_max_attempts)
        self._retry_delay_seconds = max(0.0, retry_delay_seconds)
        self._lease_seconds = max(0.1, lease_seconds)
        self._heartbeat_seconds = max(
            0.05, min(heartbeat_seconds, self._lease_seconds / 2)
        )
        self._worker_id = worker_id or f"ingestion-{uuid4().hex}"
        self._inline_execution_enabled = inline_execution_enabled
        self._alert_oldest_ready_seconds = max(0.0, alert_oldest_ready_seconds)
        self._alert_retry_wait_count = max(1, alert_retry_wait_count)
        self._alert_recent_failure_count = max(1, alert_recent_failure_count)
        self._alert_failure_window_seconds = max(1.0, alert_failure_window_seconds)
        self._scheduled: set[str] = set()
        self._schedule_lock = RLock()

    def submit(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
        company: str | None,
        year: int | None,
        doc_type: str,
        source: str,
        industry: str | None = None,
        company_aliases: list[str] | None = None,
        max_attempts: int | None = None,
    ) -> IngestionJob:
        document = self._pipeline.create_document(
            filename=filename,
            content_type=content_type,
            content=content,
            company=company,
            year=year,
            doc_type=doc_type,
            source=source,
            industry=industry,
            company_aliases=company_aliases,
        )
        now = datetime.now(UTC)
        job = IngestionJob(
            job_id=uuid4().hex,
            doc_id=document.doc_id,
            filename=document.filename,
            max_attempts=max_attempts or self._default_max_attempts,
            created_at=now,
            updated_at=now,
            events=[
                IngestionJobEvent(
                    timestamp=now,
                    status=IngestionJobStatus.QUEUED,
                    stage=DocumentProcessingStatus.WAITING.value,
                    message="Document archived and queued for processing.",
                )
            ],
        )
        self._repository.save(job)
        if self._inline_execution_enabled:
            self._enqueue(job.job_id)
        return job

    def list_jobs(self, *, limit: int = 100) -> list[IngestionJob]:
        return self._repository.list(limit=limit)

    def get_job(self, job_id: str) -> IngestionJob:
        return self._repository.get(job_id)

    def get_metrics(self) -> IngestionQueueMetrics:
        now = datetime.now(UTC)
        jobs = self._repository.list(limit=10_000)
        counts = {status: 0 for status in IngestionJobStatus}
        active_workers: set[str] = set()
        ready_times: list[datetime] = []
        cancellation_requested_count = 0
        expired_lease_count = 0
        recent_failed_count = 0
        failure_cutoff = now - timedelta(seconds=self._alert_failure_window_seconds)
        for job in jobs:
            counts[job.status] += 1
            if job.status == IngestionJobStatus.RUNNING:
                if job.lease_expires_at is not None and job.lease_expires_at <= now:
                    expired_lease_count += 1
                elif job.worker_id:
                    active_workers.add(job.worker_id)
            if job.status == IngestionJobStatus.FAILED and job.updated_at >= failure_cutoff:
                recent_failed_count += 1
            if job.cancel_requested_at is not None:
                cancellation_requested_count += 1
            if job.status == IngestionJobStatus.QUEUED:
                ready_times.append(job.created_at)
            elif (
                job.status == IngestionJobStatus.RETRY_WAIT
                and (job.available_at is None or job.available_at <= now)
            ):
                ready_times.append(job.available_at or job.updated_at)
        oldest_ready_age = None
        if ready_times:
            oldest_ready_age = max(0.0, (now - min(ready_times)).total_seconds())
        alerts: list[IngestionQueueAlert] = []
        if expired_lease_count:
            alerts.append(
                IngestionQueueAlert(
                    code="expired_worker_lease",
                    severity="critical",
                    message="Running ingestion jobs have expired worker leases.",
                    observed_value=expired_lease_count,
                    threshold=1,
                )
            )
        if recent_failed_count >= self._alert_recent_failure_count:
            alerts.append(
                IngestionQueueAlert(
                    code="recent_ingestion_failures",
                    severity="critical",
                    message="Recent ingestion failures reached the configured threshold.",
                    observed_value=recent_failed_count,
                    threshold=self._alert_recent_failure_count,
                )
            )
        if oldest_ready_age is not None and oldest_ready_age >= self._alert_oldest_ready_seconds:
            alerts.append(
                IngestionQueueAlert(
                    code="oldest_ready_age_high",
                    severity="warning",
                    message="The oldest ready ingestion job exceeded the queue-age threshold.",
                    observed_value=round(oldest_ready_age, 3),
                    threshold=self._alert_oldest_ready_seconds,
                )
            )
        retry_wait_count = counts[IngestionJobStatus.RETRY_WAIT]
        if retry_wait_count >= self._alert_retry_wait_count:
            alerts.append(
                IngestionQueueAlert(
                    code="retry_wait_backlog",
                    severity="warning",
                    message="Retry-wait ingestion jobs reached the configured threshold.",
                    observed_value=retry_wait_count,
                    threshold=self._alert_retry_wait_count,
                )
            )
        health_status = "ok"
        if any(alert.severity == "critical" for alert in alerts):
            health_status = "critical"
        elif alerts:
            health_status = "warning"
        return IngestionQueueMetrics(
            generated_at=now,
            status_counts=counts,
            active_worker_count=len(active_workers),
            cancellation_requested_count=cancellation_requested_count,
            oldest_ready_age_seconds=oldest_ready_age,
            expired_lease_count=expired_lease_count,
            recent_failed_count=recent_failed_count,
            health_status=health_status,
            alerts=alerts,
        )

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def retry(self, job_id: str) -> IngestionJob:
        job = self._repository.get(job_id)
        if job.status not in {IngestionJobStatus.FAILED, IngestionJobStatus.CANCELLED}:
            raise ValueError(f"Job {job_id} cannot be retried from status {job.status.value}.")
        now = datetime.now(UTC)
        job.status = IngestionJobStatus.QUEUED
        job.stage = DocumentProcessingStatus.WAITING.value
        job.progress_percent = 0
        job.finished_at = None
        job.error_message = None
        job.available_at = None
        job.updated_at = now
        job.events.append(
            IngestionJobEvent(
                timestamp=now,
                status=job.status,
                stage=job.stage,
                message="Manual retry requested.",
            )
        )
        self._repository.save(job)
        if self._inline_execution_enabled:
            self._enqueue(job.job_id)
        return job

    def cancel(self, job_id: str) -> IngestionJob:
        job = self._repository.get(job_id)
        if job.status == IngestionJobStatus.RUNNING:
            requested = self._repository.request_cancel(
                job_id,
                now=datetime.now(UTC),
            )
            if requested is None:
                raise ValueError(f"Job {job_id} could not be marked for cancellation.")
            return requested
        if job.status not in {IngestionJobStatus.QUEUED, IngestionJobStatus.RETRY_WAIT}:
            raise ValueError(f"Job {job_id} cannot be cancelled from status {job.status.value}.")
        now = datetime.now(UTC)
        job.status = IngestionJobStatus.CANCELLED
        job.updated_at = now
        job.finished_at = now
        job.available_at = None
        job.events.append(
            IngestionJobEvent(
                timestamp=now,
                status=job.status,
                stage=job.stage,
                progress_percent=job.progress_percent,
                message="Job cancelled before execution.",
            )
        )
        return self._repository.save(job)

    def recover_incomplete(self) -> int:
        recovered = 0
        for job in self._repository.list(limit=10_000):
            if job.status not in {
                IngestionJobStatus.QUEUED,
                IngestionJobStatus.RUNNING,
                IngestionJobStatus.RETRY_WAIT,
            }:
                continue
            self._enqueue(job.job_id)
            recovered += 1
        return recovered

    def _enqueue(self, job_id: str) -> None:
        with self._schedule_lock:
            if job_id in self._scheduled:
                return
            self._scheduled.add(job_id)
        self._executor.submit(self._run, job_id)

    def _run(self, job_id: str) -> None:
        claimed = False
        heartbeat_stop = Event()
        heartbeat_thread: Thread | None = None
        try:
            now = datetime.now(UTC)
            job = self._repository.claim(
                job_id,
                worker_id=self._worker_id,
                now=now,
                lease_expires_at=self._lease_deadline(now),
            )
            if job is None:
                return
            claimed = True
            job.error_message = None
            job.events.append(
                IngestionJobEvent(
                    timestamp=now,
                    status=job.status,
                    stage=job.stage,
                    progress_percent=job.progress_percent,
                    message=(
                        f"Processing attempt {job.attempt} started by worker "
                        f"{self._worker_id}."
                    ),
                )
            )
            if self._repository.save_owned(job, worker_id=self._worker_id) is None:
                return
            heartbeat_thread = Thread(
                target=self._heartbeat_loop,
                args=(job_id, heartbeat_stop),
                name=f"ingestion-heartbeat-{job_id[:8]}",
                daemon=True,
            )
            heartbeat_thread.start()

            record = self._pipeline.process_document(
                job.doc_id,
                progress_callback=lambda item: self._record_progress(job_id, item),
            )
            if record.status == DocumentProcessingStatus.COMPLETED:
                self._finish_success(job_id)
            else:
                self._finish_failure(job_id, record.error_message or "Document processing failed.")
        except DocumentProcessingCancelledError:
            if claimed:
                self._finish_cancelled(job_id)
        except Exception as exc:  # noqa: BLE001
            if claimed:
                self._finish_failure(job_id, f"{type(exc).__name__}: {exc}")
        finally:
            heartbeat_stop.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=self._heartbeat_seconds + 0.1)
            with self._schedule_lock:
                self._scheduled.discard(job_id)

    def _lease_deadline(self, now: datetime) -> datetime:
        return now + timedelta(seconds=self._lease_seconds)

    def _heartbeat_loop(self, job_id: str, stop: Event) -> None:
        while not stop.wait(self._heartbeat_seconds):
            now = datetime.now(UTC)
            renewed = self._repository.heartbeat(
                job_id,
                worker_id=self._worker_id,
                now=now,
                lease_expires_at=self._lease_deadline(now),
            )
            if not renewed:
                return

    def _record_progress(self, job_id: str, record: DocumentRecord) -> None:
        job = self._repository.get(job_id)
        if job.worker_id != self._worker_id:
            return
        if job.cancel_requested_at is not None:
            raise DocumentProcessingCancelledError(
                f"Cancellation requested for ingestion job {job_id}."
            )
        now = datetime.now(UTC)
        job.stage = record.status.value
        job.progress_percent = _STAGE_PROGRESS[record.status]
        job.updated_at = now
        job.heartbeat_at = now
        job.lease_expires_at = self._lease_deadline(now)
        job.error_message = record.error_message
        job.events.append(
            IngestionJobEvent(
                timestamp=now,
                status=job.status,
                stage=job.stage,
                progress_percent=job.progress_percent,
                message=record.error_message,
            )
        )
        self._repository.save_owned(job, worker_id=self._worker_id)

    def _finish_success(self, job_id: str) -> None:
        job = self._repository.get(job_id)
        if job.worker_id != self._worker_id:
            return
        now = datetime.now(UTC)
        job.status = IngestionJobStatus.SUCCEEDED
        job.stage = DocumentProcessingStatus.COMPLETED.value
        job.progress_percent = 100
        job.updated_at = now
        job.finished_at = now
        job.available_at = None
        job.worker_id = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.error_message = None
        job.events.append(
            IngestionJobEvent(
                timestamp=now,
                status=job.status,
                stage=job.stage,
                progress_percent=100,
                message="Document processing completed.",
            )
        )
        self._repository.save_owned(job, worker_id=self._worker_id)

    def _finish_failure(self, job_id: str, message: str) -> None:
        job = self._repository.get(job_id)
        if job.worker_id != self._worker_id:
            return
        now = datetime.now(UTC)
        job.error_message = message
        job.updated_at = now
        if job.attempt < job.max_attempts:
            job.status = IngestionJobStatus.RETRY_WAIT
            job.worker_id = None
            job.heartbeat_at = None
            job.lease_expires_at = None
            job.available_at = now + timedelta(seconds=self._retry_delay_seconds)
            job.events.append(
                IngestionJobEvent(
                    timestamp=now,
                    status=job.status,
                    stage=job.stage,
                    progress_percent=job.progress_percent,
                    message=f"{message} Retrying automatically.",
                )
            )
            saved = self._repository.save_owned(job, worker_id=self._worker_id)
            if saved is None:
                return
            timer = Timer(
                max(0.05, self._retry_delay_seconds),
                self._retry_after_delay,
                args=(job_id,),
            )
            timer.daemon = True
            timer.start()
            return

        job.status = IngestionJobStatus.FAILED
        job.finished_at = now
        job.worker_id = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.available_at = None
        job.events.append(
            IngestionJobEvent(
                timestamp=now,
                status=job.status,
                stage=job.stage,
                progress_percent=job.progress_percent,
                message=message,
            )
        )
        self._repository.save_owned(job, worker_id=self._worker_id)

    def _retry_after_delay(self, job_id: str) -> None:
        job = self._repository.get(job_id)
        if job.status != IngestionJobStatus.RETRY_WAIT:
            return
        job.status = IngestionJobStatus.QUEUED
        job.updated_at = datetime.now(UTC)
        job.available_at = None
        self._repository.save(job)
        self._enqueue(job_id)

    def _finish_cancelled(self, job_id: str) -> None:
        job = self._repository.get(job_id)
        if job.worker_id != self._worker_id:
            return
        now = datetime.now(UTC)
        job.status = IngestionJobStatus.CANCELLED
        job.updated_at = now
        job.finished_at = now
        job.available_at = None
        job.worker_id = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.error_message = None
        job.events.append(
            IngestionJobEvent(
                timestamp=now,
                status=job.status,
                stage=job.stage,
                progress_percent=job.progress_percent,
                message="Job cancelled at a pipeline stage boundary.",
            )
        )
        self._repository.save_owned(job, worker_id=self._worker_id)
