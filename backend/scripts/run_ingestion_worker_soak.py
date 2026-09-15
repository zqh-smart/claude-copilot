"""Repeated two-process PostgreSQL soak check for durable ingestion workers."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = ROOT / "data" / "reports" / "eval" / "ingestion_worker_soak.json"
WORKER_EVENT = re.compile(r"started by worker ([^.]+)\.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--jobs-per-round", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def evaluate_jobs(
    *, jobs: list, documents: list, process_results: list[dict], expected_count: int
) -> dict:
    worker_ids = {
        match.group(1)
        for job in jobs
        for event in job.events
        if event.message and (match := WORKER_EVENT.search(event.message))
    }
    checks = {
        "expected_job_count": len(jobs) == expected_count,
        "all_jobs_succeeded": len(jobs) == expected_count
        and all(job.status.value == "succeeded" for job in jobs),
        "exactly_once_attempt": all(job.attempt == 1 for job in jobs),
        "all_documents_completed": len(documents) == expected_count
        and all(document.status.value == "completed" for document in documents),
        "multiple_processes_claimed": len(worker_ids) >= 2,
        "leases_released": all(
            job.worker_id is None
            and job.heartbeat_at is None
            and job.lease_expires_at is None
            for job in jobs
        ),
        "workers_exited_cleanly": all(item["returncode"] == 0 for item in process_results),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "job_count": len(jobs),
            "document_count": len(documents),
            "worker_ids": sorted(worker_ids),
            "process_results": process_results,
        },
    }


def _reset_caches() -> None:
    from app.api import dependencies
    from app.core.config import get_settings

    get_settings.cache_clear()
    for name in dir(dependencies):
        obj = getattr(dependencies, name)
        if callable(obj) and hasattr(obj, "cache_clear"):
            obj.cache_clear()


def _worker_environment(worker_id: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "PYTHONUTF8": "1",
            "STORAGE_BACKEND": "postgres",
            "VECTOR_STORE_BACKEND": "none",
            "GRAPH_STORE_BACKEND": "none",
            "INGESTION_INLINE_EXECUTION_ENABLED": "false",
            "INGESTION_WORKER_COUNT": "1",
            "INGESTION_WORKER_ID": worker_id,
            "INGESTION_LEASE_SECONDS": "5",
            "INGESTION_HEARTBEAT_SECONDS": "1",
        }
    )
    return env


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    if args.rounds < 1 or args.jobs_per_round < 2:
        print("rounds must be >= 1 and jobs-per-round must be >= 2")
        return 2

    os.environ.update(
        {
            "STORAGE_BACKEND": "postgres",
            "VECTOR_STORE_BACKEND": "none",
            "GRAPH_STORE_BACKEND": "none",
            "INGESTION_INLINE_EXECUTION_ENABLED": "false",
        }
    )
    _reset_caches()

    from app.api import dependencies

    service = dependencies.get_ingestion_job_service()
    document_repository = dependencies.get_document_repository()
    job_ids: list[str] = []
    process_results: list[dict] = []
    started = time.perf_counter()
    try:
        for round_index in range(args.rounds):
            round_job_ids: list[str] = []
            for job_index in range(args.jobs_per_round):
                sequence = round_index * args.jobs_per_round + job_index
                content = (
                    f"# Worker soak document {sequence}\n\n"
                    "Revenue increased while liquidity risk remained controlled.\n"
                ).encode()
                job = service.submit(
                    filename=f"worker-soak-{sequence}.md",
                    content_type="text/markdown",
                    content=content,
                    company=f"Worker Soak Company {sequence}",
                    year=2025,
                    doc_type="annual_report",
                    source="ingestion_worker_soak",
                    max_attempts=2,
                )
                round_job_ids.append(job.job_id)
                job_ids.append(job.job_id)

            workers = []
            for worker_index in range(2):
                worker_id = f"soak-r{round_index}-w{worker_index}"
                workers.append(
                    (
                        worker_id,
                        subprocess.Popen(
                            [
                                sys.executable,
                                str(ROOT / "scripts" / "run_ingestion_worker.py"),
                                "--once",
                            ],
                            cwd=ROOT,
                            env=_worker_environment(worker_id),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                        ),
                    )
                )
            for worker_id, process in workers:
                stdout, stderr = process.communicate(timeout=args.timeout_seconds)
                process_results.append(
                    {
                        "worker_id": worker_id,
                        "returncode": process.returncode,
                        "stdout_tail": stdout[-500:],
                        "stderr_tail": stderr[-500:],
                    }
                )

            round_jobs = [service.get_job(job_id) for job_id in round_job_ids]
            if not all(job.status.value == "succeeded" for job in round_jobs):
                break

        jobs = [service.get_job(job_id) for job_id in job_ids]
        documents = [document_repository.get(job.doc_id) for job in jobs]
        report = evaluate_jobs(
            jobs=jobs,
            documents=documents,
            process_results=process_results,
            expected_count=args.rounds * args.jobs_per_round,
        )
        report["metrics"]["rounds"] = args.rounds
        report["metrics"]["jobs_per_round"] = args.jobs_per_round
        report["metrics"]["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 3
    finally:
        service.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
