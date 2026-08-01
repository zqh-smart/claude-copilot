from types import SimpleNamespace

from scripts.run_pdf_table_stress_eval import evaluate_result


def _expectations() -> dict:
    return {
        "sample": "table-scan",
        "page": {"page_number": 86, "expected_total_pages": 174},
        "thresholds": {
            "expected_route": "mineru_pdf",
            "expected_backend": "mineru",
            "max_source_text_coverage": 0.0,
            "min_table_count": 1,
            "min_row_count": 2,
            "expected_headers": ["项目", "2021年", "2020年"],
            "required_rows": {"货币资金": ["100", "90"]},
        },
    }


def _result(*, source_block_id: str | None = "block-1"):
    table = SimpleNamespace(
        page=86,
        rows=[["货币资金", "100", "90"], ["应收票据", "20", "10"]],
        headers=["项目", "2021年", "2020年"],
        source_block_id=source_block_id,
    )
    return SimpleNamespace(
        tables=[table],
        issues=[],
        metadata=SimpleNamespace(
            parse_route="mineru_pdf",
            parse_backend="mineru",
            parsed_page_range=(86, 86),
        ),
    )


def test_table_stress_requires_structured_rows_and_provenance() -> None:
    report = evaluate_result(
        result=_result(),
        source_page_count=174,
        source_text_coverage=0.0,
        expectations=_expectations(),
    )

    assert report["passed"] is True
    assert all(report["checks"].values())


def test_table_stress_rejects_missing_source_block() -> None:
    report = evaluate_result(
        result=_result(source_block_id=None),
        source_page_count=174,
        source_text_coverage=0.0,
        expectations=_expectations(),
    )

    assert report["passed"] is False
    assert report["checks"]["source_block_bound"] is False
