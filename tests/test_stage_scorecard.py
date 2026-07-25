from __future__ import annotations

from app.pipeline.feature_pipeline.evaluation.source_grounding import SourceGroundingService
from app.pipeline.feature_pipeline.evaluation.stage_scorecard import StageScorecardService
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    DocumentSegment,
    FinancialMetricFact,
    FinancialSchema,
    FinancialStatementSchema,
    ParsedDocument,
    ParsedPageBlock,
    ParsedSection,
    ParsedTable,
    ParseQualityReport,
)


def _doc(
    *,
    blocks: list[ParsedPageBlock],
    sections: list[ParsedSection] | None = None,
    schema: FinancialSchema | None = None,
    year: int = 2021,
) -> ParsedDocument:
    return ParsedDocument(
        doc_id="test-doc",
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="unit",
            filename="test.pdf",
            extension=".pdf",
            year=year,
            page_count=2,
        ),
        page_blocks=blocks,
        sections=sections or [],
        tables=[],
        quality=ParseQualityReport(text_coverage=1.0, confidence=0.9),
        financial_schema=schema,
    )


def test_stage_scorecard_core_metric_and_compare_verdict() -> None:
    blocks = [
        ParsedPageBlock(block_id="b1", page=1, block_type="paragraph", text="营业收入 100"),
        ParsedPageBlock(block_id="b2", page=1, block_type="header", text="页眉"),
        ParsedPageBlock(block_id="b3", page=2, block_type="paragraph", text="第1章 概述 ..... 1"),
    ]
    cleaned_blocks = blocks[:1]
    sections = [
        ParsedSection(
            section_id="s1",
            title="管理层讨论与分析",
            content="",
            section_type="management_discussion",
            page_start=1,
            page_end=1,
            metadata={"source": "semantic_segmentation"},
        )
    ]
    schema = FinancialSchema(
        statements=[
            FinancialStatementSchema(
                table_id="st1",
                statement_type="income_statement",
                title="合并利润表",
                period_headers=["2021", "2020"],
                metrics={"revenue": {"2021": 100.0, "2020": 80.0}},
            )
        ],
        metric_facts=[
            FinancialMetricFact(
                metric_key="revenue",
                period="2021",
                value=100.0,
                source_table_id="t1",
            )
        ],
        metrics_index={"revenue": {"2021": 100.0, "2020": 80.0}},
    )
    segments = [
        DocumentSegment(
            segment_id="seg1",
            document_id="test-doc",
            position=0,
            content="这是一段足够长的章节内容用于评估，需要超过四十个字符才能不算 tiny segment。",
            metadata={"content_type": "semantic_section"},
        ),
        DocumentSegment(
            segment_id="seg2",
            document_id="test-doc",
            position=1,
            content="短",
            metadata={"content_type": "paragraph"},
        ),
    ]

    parsed = _doc(blocks=blocks)
    cleaned = _doc(blocks=cleaned_blocks)
    segmented = _doc(blocks=cleaned_blocks, sections=sections)
    schemed = _doc(blocks=cleaned_blocks, sections=sections, schema=schema)

    service = StageScorecardService()
    scorecard = service.build(
        parsed=parsed,
        cleaned=cleaned,
        segmented=segmented,
        schemed=schemed,
        segments=segments,
        timings={"parse": 1.0, "cleaning": 0.1, "segmentation": 0.1, "schema": 0.1, "chunking": 0.1},
        expectations={
            "required_semantic_section_types": ["management_discussion", "financial_statement"],
            "core_metrics": {"revenue": {"2021": 100, "2020": 80}},
        },
    )

    assert scorecard["stages"]["schema"]["core_metric_exact_match"] == 1.0
    assert scorecard["stages"]["segmentation"]["required_section_types_hit"] == 0.5
    assert scorecard["stages"]["chunking"]["tiny_segment_ratio"] == 0.5
    assert scorecard["summary_scores"]["core_metric_exact_match"] == 1.0
    # Value 100 is too short for digit-normalized match unless literal/table path hits.
    assert scorecard["stages"]["schema"]["source_grounding_rate"] is not None

    worse = {
        **scorecard,
        "stages": {
            **scorecard["stages"],
            "schema": {**scorecard["stages"]["schema"], "core_metric_exact_match": 0.5},
        },
        "summary_scores": {**scorecard["summary_scores"], "core_metric_exact_match": 0.5},
    }
    diff = service.compare(current=worse, baseline=scorecard)
    assert diff["net_verdict"] == "negative"


def test_source_grounding_finds_value_in_table_and_corpus() -> None:
    table = ParsedTable(
        table_id="t1",
        title="合并利润表",
        raw_markdown="| 项目 | 2021 |\n| 营业收入 | 931,944,638 |",
        headers=["项目", "2021"],
        rows=[["营业收入", "931,944,638"]],
    )
    document = ParsedDocument(
        doc_id="g1",
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="unit",
            filename="g.pdf",
            extension=".pdf",
            year=2021,
        ),
        raw_text="营业收入 931,944,638 元",
        tables=[table],
        financial_schema=FinancialSchema(
            metric_facts=[
                FinancialMetricFact(
                    metric_key="revenue",
                    period="2021",
                    value=931944638,
                    source_table_id="t1",
                ),
                FinancialMetricFact(
                    metric_key="revenue",
                    period="2020",
                    value=999999999999,
                    source_table_id="t1",
                ),
            ]
        ),
    )
    report = SourceGroundingService().evaluate(document)
    assert report["source_grounding_rate"] == 0.5
    assert report["source_table_grounding_rate"] == 0.5
    assert report["ungrounded_fact_count"] == 1
