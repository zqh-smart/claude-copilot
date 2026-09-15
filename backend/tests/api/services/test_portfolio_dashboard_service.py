"""Tests for portfolio dashboard aggregation."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.api.services.portfolio_dashboard_service import PortfolioDashboardService
from src.claude_copilot.schemas.dashboard import PortfolioDashboardRequest
from src.claude_copilot.schemas.financial_data import (
    CompanySummary,
    MetricGrowthPoint,
    MetricTrendResponse,
)
from src.claude_copilot.schemas.knowledge_graph import CompanyKnowledgeGraph, KnowledgeGraphNode


def _trend(company_id: str, company_name: str, value: float) -> MetricTrendResponse:
    return MetricTrendResponse(
        company=CompanySummary(company_id=company_id, name=company_name),
        metric_key="revenue",
        unit="元",
        currency="CNY",
        points=[
            MetricGrowthPoint(
                year=2023,
                period="2023",
                value=value,
                document_id=f"doc-{company_id}",
            )
        ],
    )


def test_dashboard_builds_rankings_risks_industries_and_overlap() -> None:
    financial = MagicMock()
    financial.list_companies.return_value = [
        CompanySummary(company_id="a", name="甲公司"),
        CompanySummary(company_id="b", name="乙公司"),
    ]
    financial.metric_trend.side_effect = [
        _trend("a", "甲公司", 100.0),
        _trend("b", "乙公司", 200.0),
    ]
    graph_store = MagicMock()
    graph_store.get_company.side_effect = [
        CompanyKnowledgeGraph(
            company_id="a",
            nodes=[
                KnowledgeGraphNode(node_id="i-a", node_type="industry", name="医药"),
                KnowledgeGraphNode(node_id="r-a", node_type="risk", name="市场需求风险"),
                KnowledgeGraphNode(node_id="s-a", node_type="business_segment", name="原料药"),
            ],
        ),
        CompanyKnowledgeGraph(
            company_id="b",
            nodes=[
                KnowledgeGraphNode(node_id="i-b", node_type="industry", name="医药"),
                KnowledgeGraphNode(node_id="r-b", node_type="risk", name="合规监管风险"),
                KnowledgeGraphNode(node_id="s-b", node_type="business_segment", name="原料药"),
                KnowledgeGraphNode(node_id="s-b2", node_type="business_segment", name="制剂"),
            ],
        ),
    ]

    result = PortfolioDashboardService(financial, graph_store).build(
        PortfolioDashboardRequest(company_ids=["a", "b"], metric_keys=["revenue"])
    )

    assert [item.company_id for item in result.rankings[0].items] == ["b", "a"]
    assert result.industry_distribution[0].industry == "医药"
    assert result.industry_distribution[0].company_count == 2
    assert result.risk_heatmap[0].categories["market"] == 1
    assert result.risk_heatmap[1].categories["legal"] == 1
    assert result.business_overlap[0].shared_segments == ["原料药"]
    assert result.business_overlap[0].score == 0.5
    assert result.warnings == []


def test_dashboard_deduplicates_ids_and_reports_missing_evidence() -> None:
    financial = MagicMock()
    financial.list_companies.return_value = [CompanySummary(company_id="a", name="甲公司")]
    financial.metric_trend.return_value = MetricTrendResponse(
        company=CompanySummary(company_id="a", name="甲公司"),
        metric_key="revenue",
        warnings=["no observations"],
    )
    graph_store = MagicMock()
    graph_store.get_company.return_value = CompanyKnowledgeGraph(company_id="a")

    result = PortfolioDashboardService(financial, graph_store).build(
        PortfolioDashboardRequest(company_ids=["a", "a", "missing"], metric_keys=["revenue"])
    )

    assert result.company_ids == ["a"]
    assert result.industry_distribution[0].industry == "未分类"
    assert "company not found: missing" in result.warnings
    assert "no risk nodes available for selected companies" in result.warnings
    graph_store.get_company.assert_called_once_with("a")
