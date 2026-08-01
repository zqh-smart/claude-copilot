"""Run the durable document-ingestion worker loop outside the API process."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.dependencies import get_ingestion_job_service  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    return parser


def run_worker_iteration() -> int:
    return get_ingestion_job_service().recover_incomplete()


def main() -> int:
    args = build_parser().parse_args()
    service = get_ingestion_job_service()
    try:
        while True:
            service.recover_incomplete()
            if args.once:
                break
            time.sleep(max(0.05, args.poll_seconds))
    except KeyboardInterrupt:
        pass
    finally:
        service.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
