from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies import get_ingestion_job_service
from app.api.services.ingestion_job_service import IngestionJobService
from app.core.db import (
    LocalDocumentRepository,
    LocalIngestionJobRepository,
    LocalSegmentRepository,
)
from app.core.kg import LocalKnowledgeGraphStore
from app.core.storage import LocalFileStorage
from app.main import app
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService
from src.claude_copilot.schemas.document import DocumentProcessingStatus
from src.claude_copilot.schemas.ingestion import IngestionJob, IngestionJobStatus


def _build_job_service(
    base_dir: Path,
    *,
    max_attempts: int = 2,
    inline_execution_enabled: bool = True,
    alert_oldest_ready_seconds: float = 300.0,
) -> IngestionJobService:
    parsed_dir = base_dir / "parsed"
    pipeline = DocumentPipelineService(
        document_repository=LocalDocumentRepository(str(parsed_dir)),
        segment_repository=LocalSegmentRepository(str(parsed_dir)),
        storage=LocalFileStorage(),
        document_storage_path=str(base_dir / "documents"),
        raw_data_path=str(base_dir / "raw"),
        parsed_data_path=str(parsed_dir),
        graph_store=LocalKnowledgeGraphStore(str(base_dir / "graph")),
    )
    return IngestionJobService(
        pipeline_service=pipeline,
        repository=LocalIngestionJobRepository(str(parsed_dir)),
        worker_count=1,
        default_max_attempts=max_attempts,
        retry_delay_seconds=0.05,
        inline_execution_enabled=inline_execution_enabled,
        alert_oldest_ready_seconds=alert_oldest_ready_seconds,
    )


def _wait_for_terminal(service: IngestionJobService, job_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if job.status in {
            IngestionJobStatus.SUCCEEDED,
            IngestionJobStatus.FAILED,
            IngestionJobStatus.CANCELLED,
        }:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout} seconds")


def test_worker_shutdown_wait_drains_queued_jobs(tmp_path: Path, monkeypatch) -> None:
    service = _build_job_service(tmp_path)
    original_process = service._pipeline.process_document

    def slow_process(*args, **kwargs):
        time.sleep(0.05)
        return original_process(*args, **kwargs)

    monkeypatch.setattr(service._pipeline, "process_document", slow_process)
    jobs = [
        service.submit(
            filename=f"drain-{index}.txt",
            content_type="text/plain",
            content=f"Revenue {index}".encode(),
            company=f"Drain Company {index}",
            year=2025,
            doc_type="annual_report",
            source="test",
        )
        for index in range(3)
    ]

    service.shutdown(wait=True)

    assert all(service.get_job(job.job_id).status == IngestionJobStatus.SUCCEEDED for job in jobs)


def test_async_upload_exposes_durable_progress_and_events(tmp_path: Path) -> None:
    service = _build_job_service(tmp_path)
    app.dependency_overrides[get_ingestion_job_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        "/api/v1/documents/upload/async",
        files={"file": ("report.txt", b"Revenue increased. Liquidity risk remains.")},
        data={"company": "Async Bank", "year": "2025", "doc_type": "annual_report"},
    )

    assert response.status_code == 202
    submitted = response.json()
    completed = _wait_for_terminal(service, submitted["job_id"])
    assert completed.status == IngestionJobStatus.SUCCEEDED
    assert completed.progress_percent == 100
    assert completed.stage == "completed"
    assert completed.attempt == 1
    assert completed.worker_id is None
    assert completed.heartbeat_at is None
    assert completed.lease_expires_at is None
    assert {event.stage for event in completed.events} >= {
        "waiting",
        "parsing",
        "cleaning",
        "chunking",
        "indexing",
        "completed",
    }

    detail = client.get(f"/api/v1/documents/jobs/{completed.job_id}")
    assert detail.status_code == 200
    assert detail.json()["doc_id"] == completed.doc_id
    assert (tmp_path / "parsed" / "ingestion_jobs.json").exists()
    app.dependency_overrides.clear()


def test_failed_async_upload_retries_to_configured_limit(tmp_path: Path) -> None:
    service = _build_job_service(tmp_path, max_attempts=2)
    job = service.submit(
        filename="unsupported.bin",
        content_type="application/octet-stream",
        content=b"not a supported document",
        company=None,
        year=None,
        doc_type="unknown",
        source="test",
    )

    failed = _wait_for_terminal(service, job.job_id)
    assert failed.status == IngestionJobStatus.FAILED
    assert failed.attempt == 2
    assert "Unsupported document type" in (failed.error_message or "")
    assert any(event.status == IngestionJobStatus.RETRY_WAIT for event in failed.events)


def test_batch_async_upload_creates_one_job_per_file(tmp_path: Path) -> None:
    service = _build_job_service(tmp_path)
    app.dependency_overrides[get_ingestion_job_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        "/api/v1/documents/upload/batch/async",
        files=[
            ("files", ("a.txt", b"Revenue 100", "text/plain")),
            ("files", ("b.md", b"# Risk\nMarket risk", "text/markdown")),
        ],
        data={"company": "Batch Corp", "year": "2025"},
    )

    assert response.status_code == 202
    jobs = response.json()["jobs"]
    assert len(jobs) == 2
    assert len({item["doc_id"] for item in jobs}) == 2
    assert all(
        _wait_for_terminal(service, item["job_id"]).status == IngestionJobStatus.SUCCEEDED
        for item in jobs
    )
    app.dependency_overrides.clear()


def test_active_lease_prevents_second_service_from_processing_same_job(tmp_path: Path) -> None:
    repository = LocalIngestionJobRepository(str(tmp_path))
    now = datetime.now(UTC)
    repository.save(
        IngestionJob(
            job_id="leased-job",
            doc_id="doc-1",
            filename="report.txt",
            created_at=now,
            updated_at=now,
        )
    )
    processing_started = Event()
    allow_finish = Event()
    calls_lock = Lock()
    process_calls = 0

    class SlowPipeline:
        def process_document(self, _doc_id: str, *, progress_callback):
            nonlocal process_calls
            del progress_callback
            with calls_lock:
                process_calls += 1
            processing_started.set()
            assert allow_finish.wait(timeout=3)
            return SimpleNamespace(
                status=DocumentProcessingStatus.COMPLETED,
                error_message=None,
            )

    first = IngestionJobService(
        pipeline_service=SlowPipeline(),
        repository=repository,
        worker_count=1,
        lease_seconds=5,
        heartbeat_seconds=0.05,
        worker_id="worker-a",
    )
    second = IngestionJobService(
        pipeline_service=SlowPipeline(),
        repository=repository,
        worker_count=1,
        lease_seconds=5,
        heartbeat_seconds=0.05,
        worker_id="worker-b",
    )
    try:
        assert first.recover_incomplete() == 1
        assert processing_started.wait(timeout=3)
        assert second.recover_incomplete() == 1
        time.sleep(0.15)
        with calls_lock:
            assert process_calls == 1
        allow_finish.set()
        completed = _wait_for_terminal(first, "leased-job")
        assert completed.status == IngestionJobStatus.SUCCEEDED
    finally:
        allow_finish.set()
        first.shutdown()
        second.shutdown()


def test_api_only_service_leaves_job_queued_until_worker_dispatch(tmp_path: Path) -> None:
    service = _build_job_service(tmp_path, inline_execution_enabled=False)
    app.dependency_overrides[get_ingestion_job_service] = lambda: service
    try:
        job = service.submit(
            filename="queued.txt",
            content_type="text/plain",
            content=b"Revenue increased.",
            company="Queue Corp",
            year=2025,
            doc_type="annual_report",
            source="test",
        )
        time.sleep(0.1)
        assert service.get_job(job.job_id).status == IngestionJobStatus.QUEUED
        metrics_response = TestClient(app).get("/api/v1/documents/jobs/metrics")
        assert metrics_response.status_code == 200
        metrics = metrics_response.json()
        assert metrics["status_counts"]["queued"] == 1
        assert metrics["active_worker_count"] == 0
        assert metrics["oldest_ready_age_seconds"] >= 0

        assert service.recover_incomplete() == 1
        completed = _wait_for_terminal(service, job.job_id)
        assert completed.status == IngestionJobStatus.SUCCEEDED
    finally:
        app.dependency_overrides.clear()
        service.shutdown()


def test_running_job_is_cancelled_at_next_stage_boundary(tmp_path: Path) -> None:
    repository = LocalIngestionJobRepository(str(tmp_path))
    now = datetime.now(UTC)
    repository.save(
        IngestionJob(
            job_id="cancel-job",
            doc_id="doc-cancel",
            filename="cancel.txt",
            created_at=now,
            updated_at=now,
        )
    )
    first_stage = Event()
    continue_to_boundary = Event()

    class CancellablePipeline:
        def process_document(self, _doc_id: str, *, progress_callback):
            progress_callback(
                SimpleNamespace(
                    status=DocumentProcessingStatus.PARSING,
                    error_message=None,
                )
            )
            first_stage.set()
            assert continue_to_boundary.wait(timeout=3)
            progress_callback(
                SimpleNamespace(
                    status=DocumentProcessingStatus.CLEANING,
                    error_message=None,
                )
            )
            raise AssertionError("cancelled processing must not continue")

    service = IngestionJobService(
        pipeline_service=CancellablePipeline(),
        repository=repository,
        worker_count=1,
        worker_id="cancel-worker",
    )
    try:
        service.recover_incomplete()
        assert first_stage.wait(timeout=3)
        requested = service.cancel("cancel-job")
        assert requested.status == IngestionJobStatus.RUNNING
        assert requested.cancel_requested_at is not None
        metrics = service.get_metrics()
        assert metrics.status_counts[IngestionJobStatus.RUNNING] == 1
        assert metrics.active_worker_count == 1
        assert metrics.cancellation_requested_count == 1
        continue_to_boundary.set()

        cancelled = _wait_for_terminal(service, "cancel-job")
        assert cancelled.status == IngestionJobStatus.CANCELLED
        assert cancelled.attempt == 1
        assert not any(
            event.status == IngestionJobStatus.RETRY_WAIT
            for event in cancelled.events
        )
    finally:
        continue_to_boundary.set()
        service.shutdown()


def test_queue_metrics_emit_machine_readable_threshold_alerts(tmp_path: Path) -> None:
    service = _build_job_service(
        tmp_path,
        inline_execution_enabled=False,
        alert_oldest_ready_seconds=0,
    )
    repository = service._repository
    now = datetime.now(UTC)
    repository.save(
        IngestionJob(
            job_id="expired-lease",
            doc_id="doc-expired",
            filename="expired.txt",
            status=IngestionJobStatus.RUNNING,
            worker_id="dead-worker",
            heartbeat_at=now,
            lease_expires_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    repository.save(
        IngestionJob(
            job_id="recent-failure",
            doc_id="doc-failed",
            filename="failed.txt",
            status=IngestionJobStatus.FAILED,
            created_at=now,
            updated_at=now,
        )
    )
    repository.save(
        IngestionJob(
            job_id="old-ready",
            doc_id="doc-ready",
            filename="ready.txt",
            status=IngestionJobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
    )

    metrics = service.get_metrics()
    codes = {alert.code for alert in metrics.alerts}

    assert metrics.health_status == "critical"
    assert metrics.expired_lease_count == 1
    assert metrics.recent_failed_count == 1
    assert {"expired_worker_lease", "recent_ingestion_failures", "oldest_ready_age_high"} <= codes
    service.shutdown()
