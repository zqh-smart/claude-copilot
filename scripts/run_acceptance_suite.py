"""Thin runner for the documented acceptance suite (smoke / regression)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = Path(
    r"Z:/BaiduNetdiskDownload/阶段12：LLM大型复杂项目实战"
    r"/项目实战2：大模型金融对话交互系统/allpdf-part1"
)

SMOKE = {
    "name": "znz_2021",
    "pdf": PDF_DIR
    / "2022-01-25__北京指南针科技发展股份有限公司__300803__指南针__2021年__年度报告.pdf",
    "golden": ROOT / "data" / "golden" / "znz_2021_stage_expectations.json",
    "scorecard": ROOT / "data" / "reports" / "eval" / "latest_scorecard.json",
}
REGRESSION = {
    "name": "jucan_2021",
    "pdf": PDF_DIR
    / "2022-01-29__聚灿光电科技股份有限公司__300708__聚灿光电__2021年__年度报告.pdf",
    "golden": ROOT / "data" / "golden" / "jucan_2021_stage_expectations.json",
    "scorecard": ROOT / "data" / "reports" / "eval" / "jucan_2021_scorecard.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run acceptance suite profiles")
    parser.add_argument(
        "--profile",
        choices=("smoke", "regression", "all"),
        default="smoke",
    )
    parser.add_argument(
        "--skip-serving",
        action="store_true",
        help="Only run stage_eval (L1/L2), skip Serving+L3 ingest eval",
    )
    parser.add_argument(
        "--allow-hash-fallback",
        action="store_true",
        help="Forward to serving ingest when Silicon is unavailable",
    )
    return parser.parse_args()


def _golden_status(path: Path) -> str:
    if not path.exists():
        return "missing"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload.get("status") or "ready")


def _run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=ROOT)
    return int(completed.returncode)


def _run_sample(sample: dict, *, skip_serving: bool, allow_hash_fallback: bool) -> int:
    status = _golden_status(sample["golden"])
    print(json.dumps({"sample": sample["name"], "golden_status": status}, ensure_ascii=False))
    if status == "skeleton":
        print(
            "SKIP: golden is skeleton. Fill core_metrics then set status=ready. "
            "See docs/acceptance_suite.md §5."
        )
        return 0
    if not sample["pdf"].exists():
        print(f"MISSING_PDF {sample['pdf']}")
        return 1

    code = _run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_stage_eval.py"),
            "--pdf-path",
            str(sample["pdf"]),
            "--expectations",
            str(sample["golden"]),
            "--output",
            str(sample["scorecard"]),
        ]
    )
    if code != 0:
        return code
    if skip_serving:
        return 0
    serving_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_serving_ingest_eval.py"),
        "--pdf-path",
        str(sample["pdf"]),
        "--expectations",
        str(sample["golden"]),
        "--storage-backend",
        "postgres",
        "--vector-backend",
        "qdrant",
        "--graph-backend",
        "neo4j",
    ]
    if allow_hash_fallback:
        serving_cmd.append("--allow-hash-fallback")
    return _run(serving_cmd)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    samples: list[dict] = []
    if args.profile in {"smoke", "all"}:
        samples.append(SMOKE)
    if args.profile in {"regression", "all"}:
        samples.append(REGRESSION)

    worst = 0
    for sample in samples:
        code = _run_sample(
            sample,
            skip_serving=args.skip_serving,
            allow_hash_fallback=args.allow_hash_fallback,
        )
        worst = max(worst, code)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
