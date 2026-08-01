"""Aggregate SQL metric facts and graph evidence for P7f dashboards."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from app.api.services.financial_data_service import FinancialDataService
from app.core.errors import CompanyNotFoundError
from app.core.kg import KnowledgeGraphStoreProtocol
from src.claude_copilot.schemas.dashboard import (
    BusinessOverlap,
    CompanyMetricSnapshot,
    CompanyRiskProfile,
    IndustryDistribution,
    MetricRanking,
    PortfolioDashboardRequest,
    PortfolioDashboardResponse,
)

RISK_CATEGORIES = ("market", "financial", "operational", "legal", "other")
RISK_TERMS = {
    "market": ("市场", "需求", "价格", "竞争", "market", "demand", "price"),
    "financial": ("财务", "流动性", "偿债", "信用", "汇率", "financial", "liquidity", "credit"),
    "operational": ("经营", "供应", "生产", "技术", "安全", "operation", "supply", "technology"),
    "legal": ("法律", "合规", "诉讼", "监管", "legal", "compliance", "regulation"),
}


class PortfolioDashboardService:
    def __init__(
        self,
        financial_data: FinancialDataService,
        graph_store: KnowledgeGraphStoreProtocol,
    ) -> None:
        self._financial_data = financial_data
        self._graph_store = graph_store

    def build(self, request: PortfolioDashboardRequest) -> PortfolioDashboardResponse:
        company_ids = list(dict.fromkeys(request.company_ids))
        companies = {item.company_id: item for item in self._financial_data.list_companies()}
        selected = [companies[item] for item in company_ids if item in companies]
        warnings = [f"company not found: {item}" for item in company_ids if item not in companies]

        graphs = {
            company.company_id: self._graph_store.get_company(company.company_id)
            for company in selected
        }
        rankings = [
            self._ranking(
                company_ids=[item.company_id for item in selected],
                metric_key=metric,
                warnings=warnings,
            )
            for metric in dict.fromkeys(request.metric_keys)
        ]

        industries: dict[str, set[str]] = defaultdict(set)
        risk_profiles: list[CompanyRiskProfile] = []
        segments: dict[str, set[str]] = {}
        for company in selected:
            graph = graphs[company.company_id]
            company_industries = {
                node.name.strip()
                for node in graph.nodes
                if node.node_type == "industry" and node.name.strip()
            }
            for industry in company_industries or {"未分类"}:
                industries[industry].add(company.company_id)

            categories = {key: 0 for key in RISK_CATEGORIES}
            risk_nodes = {node.node_id: node for node in graph.nodes if node.node_type == "risk"}
            for node in risk_nodes.values():
                categories[self._risk_category(f"{node.name} {node.properties}")] += 1
            risk_profiles.append(
                CompanyRiskProfile(
                    company_id=company.company_id,
                    company_name=company.name,
                    categories=categories,
                    total=len(risk_nodes),
                )
            )
            segments[company.company_id] = {
                node.name.strip().casefold()
                for node in graph.nodes
                if node.node_type == "business_segment" and node.name.strip()
            }

        distribution = [
            IndustryDistribution(
                industry=industry,
                company_count=len(ids),
                company_ids=sorted(ids),
            )
            for industry, ids in sorted(
                industries.items(), key=lambda item: (-len(item[1]), item[0])
            )
        ]
        overlaps = [
            self._business_overlap(company_a, company_b, segments)
            for company_a, company_b in combinations([item.company_id for item in selected], 2)
        ]
        if selected and not any(item.total for item in risk_profiles):
            warnings.append("no risk nodes available for selected companies")
        if len(selected) >= 2 and not any(item.shared_segments for item in overlaps):
            warnings.append("no shared business segments found")
        return PortfolioDashboardResponse(
            company_ids=[item.company_id for item in selected],
            rankings=rankings,
            industry_distribution=distribution,
            risk_heatmap=risk_profiles,
            business_overlap=overlaps,
            warnings=warnings,
        )

    def _ranking(
        self,
        *,
        company_ids: list[str],
        metric_key: str,
        warnings: list[str],
    ) -> MetricRanking:
        items: list[CompanyMetricSnapshot] = []
        dimensions: set[tuple[str | None, str | None]] = set()
        for company_id in company_ids:
            try:
                trend = self._financial_data.metric_trend(
                    company_id,
                    metric_key,
                    start_year=None,
                    end_year=None,
                )
            except CompanyNotFoundError:
                continue
            if not trend.points:
                continue
            latest = trend.points[-1]
            dimensions.add((trend.unit, trend.currency))
            items.append(
                CompanyMetricSnapshot(
                    company_id=company_id,
                    company_name=trend.company.name,
                    year=latest.year,
                    value=latest.value,
                    unit=trend.unit,
                    currency=trend.currency,
                )
            )
        if len(dimensions) > 1:
            warnings.append(f"{metric_key}: rankings contain inconsistent unit/currency dimensions")
        items.sort(key=lambda item: (-item.value, item.company_name))
        return MetricRanking(metric_key=metric_key, items=items)

    @staticmethod
    def _risk_category(text: str) -> str:
        normalized = text.casefold()
        for category, terms in RISK_TERMS.items():
            if any(term in normalized for term in terms):
                return category
        return "other"

    @staticmethod
    def _business_overlap(
        company_a: str,
        company_b: str,
        segments: dict[str, set[str]],
    ) -> BusinessOverlap:
        left = segments.get(company_a, set())
        right = segments.get(company_b, set())
        union = left | right
        shared = sorted(left & right)
        return BusinessOverlap(
            company_id_a=company_a,
            company_id_b=company_b,
            shared_segments=shared,
            score=round(len(shared) / len(union), 4) if union else 0.0,
        )
