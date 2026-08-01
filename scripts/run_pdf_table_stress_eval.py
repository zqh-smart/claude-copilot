"""Verify structured-table extraction from a real image-only annual-report page."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_EXPECTATIONS = ROOT / "data" / "golden" / "gongtong_2021_table_stress.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "eval" / "gongtong_2021_table_stress.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-path", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, default=DEFAULT_EXPECTATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def evaluate_result(
    *, result, source_page_count: int, source_text_coverage: float, expectations: dict
) -> dict:
    thresholds = expectations["thresholds"]
    expected_page = expectations["page"]["page_number"]
    candidate_tables = [
        table
        for table in result.tables
        if table.page == expected_page and len(table.rows) >= thresholds["min_row_count"]
    ]
    table = candidate_tables[0] if candidate_tables else None
    rows_by_label = {row[0]: row[1:] for row in table.rows if row} if table else {}
    required_rows = thresholds["required_rows"]
    row_checks = {
        label: rows_by_label.get(label) == expected_values
        for label, expected_values in required_rows.items()
    }
    issue_codes = [issue.code for issue in result.issues]
    blocking_issues = {"mineru_backend_unavailable", "mineru_parse_failed"}
    checks = {
        "total_page_count": source_page_count == expectations["page"]["expected_total_pages"],
        "image_only_source": source_text_coverage <= thresholds["max_source_text_coverage"],
        "production_route": result.metadata.parse_route == thresholds["expected_route"],
        "production_backend": result.metadata.parse_backend == thresholds["expected_backend"],
        "original_page_number": result.metadata.parsed_page_range
        == (expected_page, expected_page),
        "table_count": len(result.tables) >= thresholds["min_table_count"],
        "large_table_found": table is not None,
        "headers": table is not None and table.headers == thresholds["expected_headers"],
        "required_rows": all(row_checks.values()),
        "source_block_bound": table is not None and table.source_block_id is not None,
        "no_backend_fallback": not blocking_issues.intersection(issue_codes),
    }
    return {
        "sample": expectations["sample"],
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "source_page_count": source_page_count,
            "source_text_coverage": source_text_coverage,
            "parsed_page_range": result.metadata.parsed_page_range,
            "table_count": len(result.tables),
            "selected_table_page": table.page if table else None,
            "selected_table_rows": len(table.rows) if table else 0,
            "selected_table_headers": table.headers if table else [],
            "row_checks": row_checks,
            "source_block_id": table.source_block_id if table else None,
            "issue_codes": issue_codes,
        },
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    expectations = json.loads(args.expectations.read_text(encoding="utf-8"))
    if expectations.get("status") != "ready":
        print("Table stress expectations are not ready.")
        return 2
    if not args.pdf_path.exists():
        print(f"MISSING_PDF {args.pdf_path}")
        return 1

    from app.pipeline.feature_pipeline.parser.pdf_parser import PdfDocumentParser
    from scripts.run_pdf_stress_eval import _source_profile
    from src.claude_copilot.schemas.document import DocumentMetadata

    content = args.pdf_path.read_bytes()
    source_page_count, source_text_coverage = _source_profile(content)
    page_id = expectations["page"]["page_id"]
    parser = PdfDocumentParser(
        backend_priority=["mineru_pdf", "ocr_pdf", "native_pdf"],
        mineru_start_page_id=page_id,
        mineru_end_page_id=page_id,
    )
    result = parser.parse(
        doc_id=expectations["sample"],
        content=content,
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="pdf_table_stress_eval",
            filename=args.pdf_path.name,
            extension=".pdf",
            company=expectations["document"]["company"],
            year=expectations["document"]["year"],
        ),
    )
    report = evaluate_result(
        result=result,
        source_page_count=source_page_count,
        source_text_coverage=source_text_coverage,
        expectations=expectations,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
