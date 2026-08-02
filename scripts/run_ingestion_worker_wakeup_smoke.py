"""Verify that a waiting external worker is woken by a newly submitted PostgreSQL job."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT = ROOT / "data" / "reports" / "eval" / "ingestion_worker_wakeup_smoke.json"


def _production_environment(worker_id: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "PYTHONUTF8": "1",
            "STORAGE_BACKEND": "postgres",
            "VECTOR_STORE_BACKEND": "none",
            "GRAPH_STORE_BACKEND": "none",
            "INGESTION_INLINE_EXECUTION_ENABLED": "false",
            "INGESTION_RECOVER_ON_STARTUP": "false",
            "INGESTION_WORKER_COUNT": "1",
            "INGESTION_WORKER_ID": worker_id,
        }
    )
    return env


def _reset_dependencies() -> None:
    from app.api import dependencies
    from app.core.config import get_settings

    get_settings.cache_clear()
    for name in dir(dependencies):
        value = getattr(dependencies, name)
        if callable(value) and hasattr(value, "cache_clear"):
            value.cache_clear()


def main() -> int:
    worker_id = f"wakeup-smoke-{uuid4().hex[:10]}"
    os.environ.update(_production_environment("wakeup-smoke-api"))
    _reset_dependencies()

    from app.api import dependencies
    from src.claude_copilot.schemas.ingestion import IngestionJobStatus

    service = dependencies.get_ingestion_job_service()
    process: subprocess.Popen[str] | None = None
    try:
        metrics = service.get_metrics()
        ready_count = sum(
            metrics.status_counts.get(status, 0)
            for status in ("queued", "running", "retry_wait")
        )
        if ready_count:
            print(f"queue must be empty before wakeup smoke; found {ready_count} ready jobs")
            return 2

        process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_ingestion_worker.py"),
                "--poll-seconds",
                "60",
                "--stop-after-dispatch",
                "1",
            ],
            cwd=ROOT,
            env=_production_environment(worker_id),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        time.sleep(1.0)
        started = time.perf_counter()
        job = service.submit(
            filename=f"worker-wakeup-{uuid4().hex}.md",
            content_type="text/markdown",
            content=b"# Annual report\n\nRevenue increased and liquidity remained stable.",
            company="Worker Wakeup Smoke",
            year=2025,
            doc_type="annual_report",
            source="ingestion_worker_wakeup_smoke",
            max_attempts=1,
        )

        deadline = time.monotonic() + 20
        completed = service.get_job(job.job_id)
        while completed.status not in {
            IngestionJobStatus.SUCCEEDED,
            IngestionJobStatus.FAILED,
        } and time.monotonic() < deadline:
            time.sleep(0.05)
            completed = service.get_job(job.job_id)

        stdout, stderr = process.communicate(timeout=10)
        elapsed = round(time.perf_counter() - started, 3)
        worker_claimed = any(worker_id in (event.message or "") for event in completed.events)
        checks = {
            "job_succeeded": completed.status == IngestionJobStatus.SUCCEEDED,
            "external_worker_claimed": worker_claimed,
            "notify_beats_poll_fallback": elapsed < 10,
            "worker_exited_cleanly": process.returncode == 0,
            "worker_reports_postgres_notify": "wakeup=postgres-notify" in stdout,
        }
        report = {
            "passed": all(checks.values()),
            "checks": checks,
            "metrics": {
                "elapsed_seconds": elapsed,
                "poll_fallback_seconds": 60,
                "worker_id": worker_id,
                "job_id": job.job_id,
                "worker_returncode": process.returncode,
                "stdout_tail": stdout[-500:],
                "stderr_tail": stderr[-500:],
            },
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 3
    finally:
        service.shutdown()
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
