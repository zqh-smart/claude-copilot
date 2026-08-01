from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from app.core.db.ingestion_job_repository import LocalIngestionJobRepository
from src.claude_copilot.schemas.ingestion import IngestionJob, IngestionJobStatus


def _queued_job(now: datetime) -> IngestionJob:
    return IngestionJob(
        job_id="job-1",
        doc_id="doc-1",
        filename="report.pdf",
        created_at=now,
        updated_at=now,
    )


def test_local_repository_allows_only_one_worker_to_claim(tmp_path) -> None:
    repository = LocalIngestionJobRepository(str(tmp_path))
    now = datetime.now(UTC)
    repository.save(_queued_job(now))

    def claim(worker_id: str):
        return repository.claim(
            "job-1",
            worker_id=worker_id,
            now=now,
            lease_expires_at=now + timedelta(seconds=30),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ["worker-a", "worker-b"]))

    winners = [job for job in results if job is not None]
    assert len(winners) == 1
    assert winners[0].status == IngestionJobStatus.RUNNING
    assert winners[0].attempt == 1
    assert winners[0].worker_id in {"worker-a", "worker-b"}


def test_local_repository_reclaims_expired_lease_and_fences_old_worker(tmp_path) -> None:
    repository = LocalIngestionJobRepository(str(tmp_path))
    now = datetime.now(UTC)
    repository.save(_queued_job(now))
    first = repository.claim(
        "job-1",
        worker_id="worker-a",
        now=now,
        lease_expires_at=now + timedelta(seconds=1),
    )
    assert first is not None

    assert repository.heartbeat(
        "job-1",
        worker_id="wrong-worker",
        now=now,
        lease_expires_at=now + timedelta(seconds=2),
    ) is False
    assert repository.claim(
        "job-1",
        worker_id="worker-b",
        now=now + timedelta(milliseconds=500),
        lease_expires_at=now + timedelta(seconds=5),
    ) is None

    second = repository.claim(
        "job-1",
        worker_id="worker-b",
        now=now + timedelta(seconds=2),
        lease_expires_at=now + timedelta(seconds=5),
    )
    assert second is not None
    assert second.worker_id == "worker-b"
    assert second.attempt == 2
    assert repository.heartbeat(
        "job-1",
        worker_id="worker-a",
        now=now + timedelta(seconds=2),
        lease_expires_at=now + timedelta(seconds=6),
    ) is False

    first.status = IngestionJobStatus.SUCCEEDED
    assert repository.save_owned(first, worker_id="worker-a") is None
    assert repository.get("job-1").worker_id == "worker-b"


def test_local_repository_claims_retry_only_after_available_at(tmp_path) -> None:
    repository = LocalIngestionJobRepository(str(tmp_path))
    now = datetime.now(UTC)
    job = _queued_job(now)
    job.status = IngestionJobStatus.RETRY_WAIT
    job.available_at = now + timedelta(seconds=1)
    repository.save(job)

    assert repository.claim(
        "job-1",
        worker_id="worker-a",
        now=now,
        lease_expires_at=now + timedelta(seconds=5),
    ) is None
    claimed = repository.claim(
        "job-1",
        worker_id="worker-a",
        now=now + timedelta(seconds=2),
        lease_expires_at=now + timedelta(seconds=5),
    )
    assert claimed is not None
    assert claimed.status == IngestionJobStatus.RUNNING
    assert claimed.available_at is None


def test_local_repository_preserves_cancel_request_against_worker_save(tmp_path) -> None:
    repository = LocalIngestionJobRepository(str(tmp_path))
    now = datetime.now(UTC)
    repository.save(_queued_job(now))
    claimed = repository.claim(
        "job-1",
        worker_id="worker-a",
        now=now,
        lease_expires_at=now + timedelta(seconds=5),
    )
    assert claimed is not None

    requested = repository.request_cancel(
        "job-1",
        now=now + timedelta(seconds=1),
    )
    assert requested is not None
    assert requested.cancel_requested_at is not None

    claimed.progress_percent = 50
    saved = repository.save_owned(claimed, worker_id="worker-a")
    assert saved is not None
    assert saved.cancel_requested_at == requested.cancel_requested_at
