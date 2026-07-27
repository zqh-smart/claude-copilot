from __future__ import annotations

from app.pipeline.feature_pipeline.evaluation.serving_gate import ServingGateService
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    DocumentSegment,
    FinancialMetricFact,
    FinancialSchema,
    FinancialStatementSchema,
    ParsedDocument,
    ParsedTable,
)


def _base_doc(*, company: str | None = "指南针", year: int | None = 2021) -> ParsedDocument:
    table = ParsedTable(
        table_id="t1",
        title="合并利润表",
        raw_markdown="| 项目 | 2021 |\n| 营业收入 | 931,944,638 |",
        headers=["项目", "2021"],
        rows=[["营业收入", "931,944,638"]],
    )
    return ParsedDocument(
        doc_id="gate-doc",
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="unit",
            filename="gate.pdf",
            extension=".pdf",
            company=company,
            year=year,
            page_count=1,
        ),
        raw_text="营业收入 931,944,638 元",
        tables=[table],
        segments=[
            DocumentSegment(
                segment_id="s1",
                document_id="gate-doc",
                position=0,
                content="管理层讨论与分析：报告期内主营业务稳定增长，收入与利润均有提升。",
                metadata={"content_type": "semantic_section", "section_type": "management_discussion"},
            ),
            DocumentSegment(
                segment_id="s2",
                document_id="gate-doc",
                position=1,
                content="短",
                metadata={"content_type": "page_block"},
            ),
        ],
        financial_schema=FinancialSchema(
            company=company,
            year=year,
            statements=[
                FinancialStatementSchema(
                    table_id="t1",
                    statement_type="income_statement",
                    title="利润表",
                    period_headers=["2021"],
                    metrics={"revenue": {"2021": 931944638}},
                )
            ],
            metric_facts=[
                FinancialMetricFact(
                    metric_key="revenue",
                    period="2021",
                    value=931944638,
                    source_table_id="t1",
                )
            ],
            metrics_index={"revenue": {"2021": 931944638}},
        ),
    )


def test_serving_gate_passes_grounded_core_metrics() -> None:
    document = _base_doc()
    gate = ServingGateService().evaluate(
        document,
        expectations={
            "core_metrics": {"revenue": {"2021": 931944638}},
            "serving_gate": {"min_source_grounding_rate": 0.95},
        },
    )
    assert gate.allow_metric_serving is True
    assert gate.failures == []
    assert "revenue::2021::931944638" in gate.grounded_fact_keys


def test_serving_gate_blocks_missing_company_and_filters_segments() -> None:
    document = _base_doc(company=None)
    service = ServingGateService()
    serving, gate = service.apply_to_document(document)
    assert gate.allow_metric_serving is False
    assert "missing_company" in gate.failures
    assert serving.financial_schema is not None
    assert serving.financial_schema.metric_facts == []
    # Segments still served, but tiny/TOC fragments are dropped.
    assert len(serving.segments) == 1
    assert "管理层讨论" in serving.segments[0].content


def test_serving_gate_blocks_ungrounded_core_metric() -> None:
    document = _base_doc()
    assert document.financial_schema is not None
    document.financial_schema.metric_facts = [
        FinancialMetricFact(
            metric_key="revenue",
            period="2021",
            value=999999999999,
            source_table_id="t1",
        )
    ]
    document.financial_schema.metrics_index = {"revenue": {"2021": 999999999999}}
    document.financial_schema.statements[0].metrics = {"revenue": {"2021": 999999999999}}
    gate = ServingGateService().evaluate(
        document,
        expectations={"core_metrics": {"revenue": {"2021": 931944638}}},
    )
    assert gate.allow_metric_serving is False
    assert any(item.startswith("core_metric_exact_match") for item in gate.failures)
