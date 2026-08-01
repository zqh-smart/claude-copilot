"""Ingest two real annual-report PDFs and verify cross-document conflict resolution."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_EXPECTATIONS = ROOT / "data" / "golden" / "guangzhou_langqi_conflict_e2e.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "eval" / "guangzhou_langqi_conflict_e2e.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run real-PDF cross-document conflict E2E")
    parser.add_argument("--pdf-path", action="append", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, default=DEFAULT_EXPECTATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _reset_caches() -> None:
    from app.api import dependencies
    from app.core.config import get_settings

    get_settings.cache_clear()
    for name in dir(dependencies):
        obj = getattr(dependencies, name)
        if callable(obj) and hasattr(obj, "cache_clear"):
            obj.cache_clear()


def _close_enough(value: object, expected: float, tolerance: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and abs(float(value) - expected) <= tolerance
    )


def evaluate_result(
    *,
    expectations: dict,
    ingest_results: list[dict],
    first_observations: list,
    final_observations: list,
    winner_warnings: list[str],
) -> dict:
    conflict = expectations["conflict"]
    tolerance = conflict["absolute_tolerance"]
    winner_doc_id = ingest_results[-1]["doc_id"] if ingest_results else None
    warning_fragment = (
        f"conflicting {conflict['metric_key']} values for {conflict['period_year']}"
    )
    first_value = first_observations[0].value if len(first_observations) == 1 else None
    final_value = final_observations[0].value if len(final_observations) == 1 else None
    final_item = final_observations[0] if len(final_observations) == 1 else None
    checks = {
        "both_documents_completed": len(ingest_results) == 2
        and all(item["status"] == "completed" for item in ingest_results),
        "real_conflicting_loser_observed": _close_enough(
            first_value,
            conflict["expected_loser_value"],
            tolerance,
        ),
        "conflict_warning_persisted": any(
            warning_fragment in warning for warning in winner_warnings
        ),
        "single_winner_persisted": len(final_observations) == 1,
        "winner_value": _close_enough(
            final_value,
            conflict["expected_winner_value"],
            tolerance,
        ),
        "winner_document": final_item is not None and final_item.document_id == winner_doc_id,
        "winner_grounded": final_item is not None
        and final_item.provenance.get("source_grounded") is True,
    }
    return {
        "sample": expectations["sample"],
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "metric_key": conflict["metric_key"],
            "period_year": conflict["period_year"],
            "first_value": first_value,
            "final_value": final_value,
            "winner_document_id": final_item.document_id if final_item else None,
            "winner_warning_count": len(winner_warnings),
            "ingest_results": ingest_results,
        },
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    expectations = json.loads(args.expectations.read_text(encoding="utf-8"))
    if expectations.get("status") != "ready":
        print("Conflict E2E expectations are not ready.")
        return 2
    if len(args.pdf_path) != len(expectations["documents"]):
        print("PDF count does not match conflict expectations.")
        return 1
    if any(not path.exists() for path in args.pdf_path):
        print("MISSING_PDF", [str(path) for path in args.pdf_path if not path.exists()])
        return 1

    os.environ["STORAGE_BACKEND"] = "postgres"
    os.environ["VECTOR_STORE_BACKEND"] = "none"
    os.environ["GRAPH_STORE_BACKEND"] = "none"
    os.environ["LLM_GROUNDED_SYNTHESIS_ENABLED"] = "false"
    _reset_caches()

    from app.api import dependencies
    from app.core.db import build_company_id
    from src.claude_copilot.schemas.document import DocumentProcessingStatus

    pipeline = dependencies.get_document_pipeline_service()
    financial = dependencies.get_financial_data_repository()
    parsed_repository = dependencies.get_parsed_document_repository()
    company_id = build_company_id(expectations["company"])
    conflict = expectations["conflict"]
    ingest_results: list[dict] = []
    first_observations: list = []

    document_pairs = zip(args.pdf_path, expectations["documents"], strict=True)
    for index, (path, document) in enumerate(document_pairs):
        record = pipeline.ingest(
            filename=path.name,
            content_type="application/pdf",
            content=path.read_bytes(),
            company=expectations["company"],
            year=document["year"],
            doc_type="annual_report",
            source="conflict_e2e",
            company_aliases=expectations["company_aliases"],
        )
        ingest_results.append(
            {
                "year": document["year"],
                "status": record.status.value,
                "doc_id": record.doc_id,
                "error": record.error_message,
            }
        )
        if record.status != DocumentProcessingStatus.COMPLETED:
            break
        if index == 0:
            first_observations = financial.query_metrics(
                company_id,
                year=conflict["period_year"],
                metric_key=conflict["metric_key"],
                limit=100,
            )

    final_observations = financial.query_metrics(
        company_id,
        year=conflict["period_year"],
        metric_key=conflict["metric_key"],
        limit=100,
    )
    winner_warnings: list[str] = []
    if len(ingest_results) == 2 and ingest_results[-1]["status"] == "completed":
        winner = parsed_repository.get(ingest_results[-1]["doc_id"])
        if winner.financial_schema is not None:
            winner_warnings = list(winner.financial_schema.metadata.get("metric_conflicts") or [])

    report = evaluate_result(
        expectations=expectations,
        ingest_results=ingest_results,
        first_observations=first_observations,
        final_observations=final_observations,
        winner_warnings=winner_warnings,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
