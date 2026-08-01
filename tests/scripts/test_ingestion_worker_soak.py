from datetime import UTC, datetime
from types import SimpleNamespace

from scripts.run_ingestion_worker_soak import evaluate_jobs


def _job(worker_id: str, *, attempt: int = 1):
    event = SimpleNamespace(message=f"Processing attempt 1 started by worker {worker_id}.")
    return SimpleNamespace(
        status=SimpleNamespace(value="succeeded"),
        attempt=attempt,
        worker_id=None,
        heartbeat_at=None,
        lease_expires_at=None,
        events=[event],
        finished_at=datetime.now(UTC),
    )


def test_worker_soak_requires_two_workers_and_exactly_once_completion() -> None:
    report = evaluate_jobs(
        jobs=[_job("worker-a"), _job("worker-b")],
        documents=[
            SimpleNamespace(status=SimpleNamespace(value="completed")),
            SimpleNamespace(status=SimpleNamespace(value="completed")),
        ],
        process_results=[{"returncode": 0}, {"returncode": 0}],
        expected_count=2,
    )

    assert report["passed"] is True
    assert report["metrics"]["worker_ids"] == ["worker-a", "worker-b"]


def test_worker_soak_rejects_retries_and_single_worker_execution() -> None:
    report = evaluate_jobs(
        jobs=[_job("worker-a", attempt=2), _job("worker-a")],
        documents=[
            SimpleNamespace(status=SimpleNamespace(value="completed")),
            SimpleNamespace(status=SimpleNamespace(value="completed")),
        ],
        process_results=[{"returncode": 0}, {"returncode": 0}],
        expected_count=2,
    )

    assert report["passed"] is False
    assert report["checks"]["exactly_once_attempt"] is False
    assert report["checks"]["multiple_processes_claimed"] is False
