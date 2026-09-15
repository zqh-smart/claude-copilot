"""Thin runner for the documented acceptance suite (smoke / regression)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_DIR = ROOT / "data" / "documents"

SMOKE = {
    "name": "znz_2021",
    "pdf": DOCUMENT_DIR / "95686a1aa6534494a1806fdc8e9d6b1c.pdf",
    "golden": ROOT / "data" / "golden" / "znz_2021_stage_expectations.json",
    "scorecard": ROOT / "data" / "reports" / "eval" / "latest_scorecard.json",
}
REGRESSION_SAMPLES = [
    {
        "name": "jucan_2021",
        "pdf": DOCUMENT_DIR / "8a73d2fbfd0d4d799d5489e24fe21bd3.pdf",
        "golden": ROOT / "data" / "golden" / "jucan_2021_stage_expectations.json",
        "scorecard": ROOT / "data" / "reports" / "eval" / "jucan_2021_scorecard.json",
    },
    {
        "name": "tianhua_2021",
        "pdf": DOCUMENT_DIR / "267bbddf6aeb4738a9b8e31de568d867.pdf",
        "golden": ROOT / "data" / "golden" / "tianhua_2021_stage_expectations.json",
        "scorecard": ROOT / "data" / "reports" / "eval" / "tianhua_2021_scorecard.json",
    },
]
STRESS = {
    "name": "gongtong_2021_scanned_pdf",
    "golden": ROOT / "data" / "golden" / "gongtong_2021_pdf_stress.json",
}
TABLE_STRESS = {
    "name": "gongtong_2021_scanned_balance_sheet",
    "golden": ROOT / "data" / "golden" / "gongtong_2021_table_stress.json",
}
CONFLICT = {
    "name": "guangzhou_langqi_2020_2021_conflict",
    "golden": ROOT / "data" / "golden" / "guangzhou_langqi_conflict_e2e.json",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run acceptance suite profiles")
    parser.add_argument(
        "--profile",
        choices=(
            "smoke",
            "regression",
            "stress",
            "table-stress",
            "conflict",
            "soak",
            "l4",
            "all",
        ),
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
    parser.add_argument(
        "--with-api",
        dest="with_api",
        action="store_true",
        default=True,
        help="After serving eval, run HTTP API smoke (default)",
    )
    parser.add_argument(
        "--skip-api",
        dest="with_api",
        action="store_false",
        help="Skip HTTP API smoke after serving eval",
    )
    parser.add_argument(
        "--skip-invariants",
        action="store_true",
        help="Skip deterministic serving-gate/conflict invariant tests",
    )
    return parser


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


def _golden_status(path: Path) -> str:
    if not path.exists():
        return "missing"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload.get("status") or "ready")


def _scope_contract_failures(payload: dict) -> list[str]:
    failures: list[str] = []
    default_scope = payload.get("default_entity_scope")
    if default_scope not in {"consolidated", "parent_company", "unknown"}:
        failures.append("default_entity_scope must be declared")
    for case in [
        *(payload.get("retrieval_cases") or []),
        *(payload.get("benchmark_cases") or []),
    ]:
        question = str(case.get("question") or "").casefold()
        expected_scope = case.get("expect_entity_scope") or default_scope
        if any(cue in question for cue in ("母公司", "parent company", "standalone")):
            if expected_scope != "parent_company":
                failures.append(f"{case.get('id')}: parent-company question has wrong scope")
        if any(cue in question for cue in ("合并", "consolidated", "group basis")):
            if expected_scope != "consolidated":
                failures.append(f"{case.get('id')}: consolidated question has wrong scope")
    return failures


def _run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=ROOT)
    return int(completed.returncode)


def _run_invariants() -> int:
    return _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(ROOT / "tests" / "test_serving_gate.py"),
            str(ROOT / "tests" / "test_serving_facts.py"),
        ]
    )


def _run_sample(
    sample: dict,
    *,
    skip_serving: bool,
    allow_hash_fallback: bool,
    with_api: bool,
) -> int:
    status = _golden_status(sample["golden"])
    print(json.dumps({"sample": sample["name"], "golden_status": status}, ensure_ascii=False))
    if status == "skeleton":
        print(
            "SKIP: golden is skeleton. Fill core_metrics then set status=ready. "
            "See docs/acceptance_suite.md §5."
        )
        return 0
    expectations = json.loads(sample["golden"].read_text(encoding="utf-8"))
    scope_failures = _scope_contract_failures(expectations)
    if scope_failures:
        print("INVALID_SCOPE_CONTRACT " + " | ".join(scope_failures))
        return 1
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
    code = _run(serving_cmd)
    if code != 0:
        return code
    if with_api:
        api_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_api_smoke.py"),
            "--golden",
            str(sample["golden"]),
            "--storage-backend",
            "postgres",
            "--vector-backend",
            "qdrant",
            "--graph-backend",
            "neo4j",
        ]
        if allow_hash_fallback:
            api_cmd.append("--allow-hash-fallback")
        return _run(api_cmd)
    return 0


def _run_stress(sample: dict) -> int:
    expectations = json.loads(sample["golden"].read_text(encoding="utf-8"))
    matches = sorted(DOCUMENT_DIR.glob(expectations["document"]["filename_glob"]))
    if len(matches) != 1:
        pattern = expectations["document"]["filename_glob"]
        print(f"STRESS_PDF_MATCH_COUNT {len(matches)} pattern={pattern}")
        return 1
    return _run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_pdf_stress_eval.py"),
            "--pdf-path",
            str(matches[0]),
            "--expectations",
            str(sample["golden"]),
        ]
    )


def _run_table_stress(sample: dict) -> int:
    expectations = json.loads(sample["golden"].read_text(encoding="utf-8"))
    matches = sorted(DOCUMENT_DIR.glob(expectations["document"]["filename_glob"]))
    if len(matches) != 1:
        pattern = expectations["document"]["filename_glob"]
        print(f"TABLE_STRESS_PDF_MATCH_COUNT {len(matches)} pattern={pattern}")
        return 1
    return _run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_pdf_table_stress_eval.py"),
            "--pdf-path",
            str(matches[0]),
            "--expectations",
            str(sample["golden"]),
        ]
    )


def _run_conflict(sample: dict) -> int:
    expectations = json.loads(sample["golden"].read_text(encoding="utf-8"))
    matches: list[Path] = []
    for document in expectations["documents"]:
        document_matches = sorted(DOCUMENT_DIR.glob(document["filename_glob"]))
        if len(document_matches) != 1:
            print(
                f"CONFLICT_PDF_MATCH_COUNT {len(document_matches)} "
                f"pattern={document['filename_glob']}"
            )
            return 1
        matches.append(document_matches[0])
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_conflict_e2e.py"),
        "--expectations",
        str(sample["golden"]),
    ]
    for path in matches:
        command.extend(["--pdf-path", str(path)])
    return _run(command)


def _run_worker_soak() -> int:
    wakeup_code = _run(
        [sys.executable, str(ROOT / "scripts" / "run_ingestion_worker_wakeup_smoke.py")]
    )
    if wakeup_code != 0:
        return wakeup_code
    return _run([sys.executable, str(ROOT / "scripts" / "run_ingestion_worker_soak.py")])


def _run_l4() -> int:
    return _run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_l4_research_eval.py"),
            "--profile",
            "all",
        ]
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    if not args.skip_invariants:
        code = _run_invariants()
        if code != 0:
            return code
    samples: list[dict] = []
    if args.profile in {"smoke", "all"}:
        samples.append(SMOKE)
    if args.profile in {"regression", "all"}:
        samples.extend(REGRESSION_SAMPLES)

    worst = 0
    for sample in samples:
        code = _run_sample(
            sample,
            skip_serving=args.skip_serving,
            allow_hash_fallback=args.allow_hash_fallback,
            with_api=args.with_api,
        )
        worst = max(worst, code)
    if args.profile in {"stress", "all"}:
        worst = max(worst, _run_stress(STRESS))
    if args.profile in {"table-stress", "all"}:
        worst = max(worst, _run_table_stress(TABLE_STRESS))
    if args.profile in {"conflict", "all"}:
        worst = max(worst, _run_conflict(CONFLICT))
    if args.profile in {"soak", "all"}:
        worst = max(worst, _run_worker_soak())
    if args.profile in {"l4", "all"}:
        worst = max(worst, _run_l4())
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
