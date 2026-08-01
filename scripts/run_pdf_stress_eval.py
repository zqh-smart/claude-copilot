"""Evaluate a real image-only annual report through the production PDF router."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_EXPECTATIONS = ROOT / "data" / "golden" / "gongtong_2021_pdf_stress.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "eval" / "gongtong_2021_pdf_stress.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the scanned-PDF stress acceptance check")
    parser.add_argument("--pdf-path", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, default=DEFAULT_EXPECTATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _source_profile(content: bytes) -> tuple[int, float]:
    import fitz

    document = fitz.open(stream=content, filetype="pdf")
    try:
        page_count = len(document)
        nonempty = sum(1 for page in document if (page.get_text("text") or "").strip())
    finally:
        document.close()
    coverage = 0.0 if page_count == 0 else nonempty / page_count
    return page_count, coverage


def evaluate_result(
    *, result, source_page_count: int, source_text_coverage: float, expectations: dict
) -> dict:
    thresholds = expectations["thresholds"]
    page_range = expectations["page_range"]
    raw_text = result.raw_text.strip()
    required_phrases = list(thresholds["required_phrases"])
    matched_phrases = [phrase for phrase in required_phrases if phrase in raw_text]
    phrase_recall = len(matched_phrases) / len(required_phrases) if required_phrases else 1.0
    quality = result.quality
    parsed_text_coverage = (
        quality.text_coverage if quality and quality.text_coverage is not None else 0.0
    )
    blocking_issue_codes = {
        "mineru_backend_unavailable",
        "mineru_parse_failed",
        "ocr_backend_unavailable",
    }
    observed_issue_codes = [issue.code for issue in result.issues]
    expected_parsed_pages = page_range["end_page_id"] - page_range["start_page_id"] + 1

    checks = {
        "total_page_count": source_page_count == page_range["expected_total_pages"],
        "image_only_source": source_text_coverage <= thresholds["max_source_text_coverage"],
        "production_route": result.metadata.parse_route == thresholds["expected_route"],
        "production_backend": result.metadata.parse_backend == thresholds["expected_backend"],
        "parsed_page_count": result.metadata.parsed_page_count == expected_parsed_pages,
        "parsed_text_coverage": parsed_text_coverage >= thresholds["min_parsed_text_coverage"],
        "extracted_chars": len(raw_text) >= thresholds["min_extracted_chars"],
        "phrase_recall": phrase_recall >= thresholds["min_phrase_recall"],
        "no_backend_fallback": not blocking_issue_codes.intersection(observed_issue_codes),
    }
    return {
        "sample": expectations["sample"],
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "source_page_count": source_page_count,
            "source_text_coverage": source_text_coverage,
            "parsed_page_count": result.metadata.parsed_page_count,
            "parsed_text_coverage": parsed_text_coverage,
            "extracted_chars": len(raw_text),
            "phrase_recall": phrase_recall,
            "matched_phrases": matched_phrases,
            "issue_codes": observed_issue_codes,
            "route": result.metadata.parse_route,
            "backend": result.metadata.parse_backend,
        },
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    expectations = json.loads(args.expectations.read_text(encoding="utf-8"))
    if expectations.get("status") != "ready":
        print("Stress expectations are not ready.")
        return 2
    if not args.pdf_path.exists():
        print(f"MISSING_PDF {args.pdf_path}")
        return 1

    from app.pipeline.feature_pipeline.parser.pdf_parser import PdfDocumentParser
    from src.claude_copilot.schemas.document import DocumentMetadata

    content = args.pdf_path.read_bytes()
    source_page_count, source_text_coverage = _source_profile(content)
    page_range = expectations["page_range"]
    parser = PdfDocumentParser(
        backend_priority=["mineru_pdf", "ocr_pdf", "native_pdf"],
        mineru_start_page_id=page_range["start_page_id"],
        mineru_end_page_id=page_range["end_page_id"],
    )
    result = parser.parse(
        doc_id=expectations["sample"],
        content=content,
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="pdf_stress_eval",
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
