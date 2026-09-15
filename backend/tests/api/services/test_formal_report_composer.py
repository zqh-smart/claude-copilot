"""Unit tests for deterministic formal multi-document report composition."""

from app.api.services.formal_report_composer import ReportSource, compose_formal_report
from src.claude_copilot.schemas.workflows import ReportOutlineResponse


def _source(doc_id: str, sections: list[dict], warnings: list[str] | None = None) -> ReportSource:
    return ReportSource(
        doc_id=doc_id,
        outline=ReportOutlineResponse(
            answer_markdown="# 单文档财务提纲报告",
            sections=sections,
            warnings=warnings or [],
        ),
    )


def test_investment_report_deduplicates_cross_source_evidence() -> None:
    report = compose_formal_report(
        report_type="investment",
        question="比较两期经营质量",
        sources=[
            _source(
                "doc-2023",
                [
                    {"title": "核心财务指标", "bullets": ["营业收入：100 亿元"]},
                    {"title": "风险提示", "bullets": ["原材料价格波动"]},
                ],
            ),
            _source(
                "doc-2024",
                [
                    {"title": "核心财务指标", "bullets": ["营业收入：100 亿元"]},
                    {"title": "增长与趋势", "bullets": ["净利润同比增长 8%"]},
                ],
            ),
        ],
    )

    core_section = report.markdown.split("# 核心财务与趋势", 1)[1].split("# 主要风险", 1)[0]
    assert core_section.count("营业收入：100 亿元") == 1
    assert "[D1][D2] 营业收入：100 亿元" in core_section
    assert "[D2] 净利润同比增长 8%" in core_section
    assert report.markdown.index("# 执行摘要") < report.markdown.index("# 核心财务与趋势")


def test_formal_report_filters_outline_disclaimer_and_keeps_real_warnings() -> None:
    report = compose_formal_report(
        report_type="risk",
        question="识别重大风险",
        sources=[
            _source(
                "doc-risk",
                [
                    {"title": "风险提示", "bullets": ["海外收入面临汇率风险"]},
                    {
                        "title": "局限与说明",
                        "bullets": ["本报告为提纲 MVP，非正式投研报告。"],
                    },
                ],
                warnings=["缺少 2022 年可比数据"],
            )
        ],
    )

    assert "# 核心风险结论" in report.markdown
    assert "# 财务暴露与缓释依据" in report.markdown
    assert "[D1] 海外收入面临汇率风险" in report.markdown
    assert "提纲 MVP" not in report.markdown
    assert report.warnings == ["doc-risk: 缺少 2022 年可比数据"]
