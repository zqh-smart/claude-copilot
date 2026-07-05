from pathlib import Path

from app.core.db import LocalSegmentRepository
from app.core.kg import LocalKnowledgeGraphStore
from app.core.rag import LocalRetriever
from app.core.rag.orchestrator import QueryAnalyzer, RetrievalOrchestrator
from src.claude_copilot.schemas.document import DocumentSegment
from src.claude_copilot.schemas.financial_data import (
    CompanySummary,
    FinancialMetricObservation,
)
from src.claude_copilot.schemas.knowledge_graph import (
    DocumentKnowledgeGraph,
    KnowledgeGraphNode,
    KnowledgeGraphRelationship,
)


class StubFinancialRepository:
    def __init__(self) -> None:
        self.company = CompanySummary(
            company_id="acme",
            name="ACME",
            years=[2022, 2023, 2024],
            document_count=1,
            metric_count=3,
        )
        self.items = [
            FinancialMetricObservation(
                company_id="acme",
                company="ACME",
                document_id="doc-1",
                document_year=2024,
                metric_key="revenue",
                period=str(year),
                period_year=year,
                value=value,
                unit="millions",
                currency="USD",
            )
            for year, value in [(2022, 100), (2023, 120), (2024, 144)]
        ]

    def list_companies(self):
        return [self.company]

    def get_company(self, company_id: str):
        return self.company if company_id == "acme" else None

    def query_metrics(
        self,
        company_id: str,
        *,
        year=None,
        metric_key=None,
        statement_type=None,
        limit=500,
    ):
        items = [
            item
            for item in self.items
            if item.company_id == company_id
            and (year is None or item.period_year == year)
            and (metric_key is None or item.metric_key == metric_key)
        ]
        return items[:limit]


def build_orchestrator(tmp_path: Path) -> RetrievalOrchestrator:
    segment_repository = LocalSegmentRepository(str(tmp_path))
    segment_repository.replace_for_document(
        "doc-1",
        [
            DocumentSegment(
                segment_id="risk",
                document_id="doc-1",
                position=1,
                content="Revenue declined because customer demand weakened.",
            )
        ],
    )
    graph_store = LocalKnowledgeGraphStore(str(tmp_path / "graph"))
    graph_store.replace_document(
        DocumentKnowledgeGraph(
            document_id="doc-1",
            company_id="acme",
            nodes=[
                KnowledgeGraphNode(
                    node_id="company:acme",
                    node_type="company",
                    name="ACME",
                ),
                KnowledgeGraphNode(
                    node_id="risk:liquidity",
                    node_type="risk",
                    name="liquidity_risk",
                    document_id="doc-1",
                    properties={"evidence": "Liquidity pressure remains a key risk."},
                ),
            ],
            relationships=[
                KnowledgeGraphRelationship(
                    relationship_id="relationship:risk",
                    relationship_type="HAS_RISK",
                    source_node_id="company:acme",
                    target_node_id="risk:liquidity",
                    document_id="doc-1",
                )
            ],
        )
    )
    return RetrievalOrchestrator(
        vector_retriever=LocalRetriever(segment_repository),
        financial_repository=StubFinancialRepository(),
        graph_store=graph_store,
    )


def test_query_analyzer_avoids_overlapping_metric_aliases() -> None:
    analysis = QueryAnalyzer().analyze("2024年净利息收入是多少？")

    assert analysis.intent == "structured"
    assert analysis.routes == ["sql"]
    assert analysis.metric_keys == ["net_interest_income"]
    assert analysis.years == [2024]


def test_orchestrator_routes_structured_query_to_sql(tmp_path: Path) -> None:
    result = build_orchestrator(tmp_path).retrieve(
        "营收增长趋势是多少？",
        doc_id="doc-1",
        company_id="acme",
        top_k=3,
    )

    assert result.analysis.intent == "structured"
    assert result.analysis.routes == ["sql"]
    assert result.vector_hits == []
    assert len(result.metrics) == 3
    assert result.calculations[0].yoy_growth == {2023: 0.2, 2024: 0.2}
    assert result.calculations[0].cagr == 0.2


def test_orchestrator_routes_explanatory_metric_query_to_both_sources(
    tmp_path: Path,
) -> None:
    result = build_orchestrator(tmp_path).retrieve(
        "为什么营收下降？请分析原因",
        doc_id="doc-1",
        company_id="acme",
        top_k=3,
    )

    assert result.analysis.intent == "hybrid"
    assert result.analysis.routes == ["vector", "sql"]
    assert result.vector_hits[0][0].segment_id == "risk"
    assert len(result.metrics) == 3


def test_orchestrator_routes_risk_query_to_vector_and_graph(tmp_path: Path) -> None:
    result = build_orchestrator(tmp_path).retrieve(
        "公司面临哪些风险？",
        doc_id="doc-1",
        company_id="acme",
        top_k=3,
    )

    assert result.analysis.intent == "hybrid"
    assert result.analysis.routes == ["vector", "graph"]
    assert result.vector_hits
    assert result.metrics == []
    assert result.graph_paths[0].relationships[0].relationship_type == "HAS_RISK"
