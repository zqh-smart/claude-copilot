from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.v1.report_studio import _attachment_header
from app.main import app
from src.claude_copilot.schemas.report_studio import ReportTemplate

client = TestClient(app)


def test_attachment_header_supports_chinese_filename() -> None:
    header = _attachment_header("指南针 2021 财务报告.pdf")

    assert header.startswith("attachment; filename=report; filename*=UTF-8''")
    assert "%E6%8C%87%E5%8D%97%E9%92%88" in header
    header.encode("latin-1")


def test_list_templates_returns_six_financial_templates() -> None:
    response = client.get("/api/v1/report/templates")

    assert response.status_code == 200
    templates = [ReportTemplate.model_validate(item) for item in response.json()]
    ids = {item.template_id for item in templates}
    assert ids == {
        "comprehensive_financial",
        "annual_operations",
        "profitability",
        "cash_and_solvency",
        "financial_risk",
        "period_comparison",
    }
    comprehensive = next(
        item for item in templates if item.template_id == "comprehensive_financial"
    )
    assert [chapter.title for chapter in comprehensive.chapters][:3] == [
        "执行摘要",
        "公司及报告期概况",
        "核心财务指标",
    ]
    margin = next(
        chapter
        for item in templates
        if item.template_id == "profitability"
        for chapter in item.chapters
        if chapter.chapter_id == "gross_margin"
    )
    assert "gross_profit" in margin.required_metrics
    assert "management_discussion" in margin.section_hints
    assert margin.must_cite is True
