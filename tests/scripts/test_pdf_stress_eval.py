import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from scripts.run_pdf_stress_eval import evaluate_result

ROOT = Path(__file__).resolve().parents[2]


def _expectations() -> dict:
    return {
        "sample": "scan",
        "page_range": {"start_page_id": 0, "end_page_id": 1, "expected_total_pages": 2},
        "thresholds": {
            "expected_route": "mineru_pdf",
            "expected_backend": "mineru",
            "max_source_text_coverage": 0.0,
            "min_parsed_text_coverage": 1.0,
            "min_extracted_chars": 8,
            "required_phrases": ["年度报告", "营业收入"],
            "min_phrase_recall": 1.0,
        },
    }


def _result(*, raw_text: str, issue_codes: list[str] | None = None):
    return SimpleNamespace(
        raw_text=raw_text,
        metadata=SimpleNamespace(
            parse_route="mineru_pdf",
            parse_backend="mineru",
            parsed_page_count=2,
        ),
        quality=SimpleNamespace(text_coverage=1.0),
        issues=[SimpleNamespace(code=code) for code in issue_codes or []],
    )


def test_pdf_stress_eval_passes_only_when_all_metrics_meet_thresholds() -> None:
    report = evaluate_result(
        result=_result(raw_text="2021年年度报告，营业收入增长。"),
        source_page_count=2,
        source_text_coverage=0.0,
        expectations=_expectations(),
    )

    assert report["passed"] is True
    assert all(report["checks"].values())


def test_pdf_stress_eval_rejects_backend_fallback_and_missing_phrase() -> None:
    report = evaluate_result(
        result=_result(raw_text="年度报告", issue_codes=["mineru_parse_failed"]),
        source_page_count=2,
        source_text_coverage=0.0,
        expectations=_expectations(),
    )

    assert report["passed"] is False
    assert report["checks"]["phrase_recall"] is False
    assert report["checks"]["no_backend_fallback"] is False


def test_pdf_stress_eval_entrypoint_imports_project_modules() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_pdf_stress_eval.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "scanned-PDF stress" in completed.stdout
