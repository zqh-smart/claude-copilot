from pathlib import Path

from app.core.kg import LocalKnowledgeGraphStore
from src.claude_copilot.schemas.knowledge_graph import (
    DocumentKnowledgeGraph,
    KnowledgeGraphNode,
    KnowledgeGraphRelationship,
)


def test_graph_search_returns_two_hop_paths(tmp_path: Path) -> None:
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
                    node_id="risk:market",
                    node_type="risk",
                    name="market_risk",
                    document_id="doc-1",
                ),
                KnowledgeGraphNode(
                    node_id="event:macro",
                    node_type="event",
                    name="macro_volatility",
                    document_id="doc-1",
                ),
            ],
            relationships=[
                KnowledgeGraphRelationship(
                    relationship_id="rel:has_risk",
                    relationship_type="HAS_RISK",
                    source_node_id="company:acme",
                    target_node_id="risk:market",
                    document_id="doc-1",
                ),
                KnowledgeGraphRelationship(
                    relationship_id="rel:affected",
                    relationship_type="AFFECTED_BY",
                    source_node_id="risk:market",
                    target_node_id="event:macro",
                    document_id="doc-1",
                ),
            ],
        )
    )

    paths = graph_store.search(
        "市场风险暴露与宏观影响",
        document_id="doc-1",
        limit=5,
    )

    two_hop = [path for path in paths if len(path.relationships) == 2]
    assert two_hop
    assert "AFFECTED_BY" in two_hop[0].summary
    assert len(two_hop[0].nodes) == 3


def test_graph_search_prefers_has_risk_over_affected_by(tmp_path: Path) -> None:
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
                    node_id="risk:market",
                    node_type="risk",
                    name="market_risk",
                    document_id="doc-1",
                ),
            ],
            relationships=[
                KnowledgeGraphRelationship(
                    relationship_id="rel:has_risk",
                    relationship_type="HAS_RISK",
                    source_node_id="company:acme",
                    target_node_id="risk:market",
                    document_id="doc-1",
                ),
                KnowledgeGraphRelationship(
                    relationship_id="rel:affected",
                    relationship_type="AFFECTED_BY",
                    source_node_id="company:acme",
                    target_node_id="risk:market",
                    document_id="doc-1",
                ),
            ],
        )
    )

    paths = graph_store.search(
        "公司面临哪些市场风险或风险暴露？",
        document_id="doc-1",
        limit=3,
    )

    assert paths
    assert paths[0].relationships[0].relationship_type == "HAS_RISK"


def test_graph_search_year_filter_drops_conflicting_paths(tmp_path: Path) -> None:
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
                    node_id="metric:rev-2020",
                    node_type="metric",
                    name="revenue",
                    document_id="doc-1",
                    properties={"period_year": 2020, "metric_key": "revenue"},
                ),
                KnowledgeGraphNode(
                    node_id="risk:market",
                    node_type="risk",
                    name="market_risk",
                    document_id="doc-1",
                    properties={"year": 2021, "risk_type": "market_risk"},
                ),
            ],
            relationships=[
                KnowledgeGraphRelationship(
                    relationship_id="rel:metric",
                    relationship_type="REPORTS_METRIC",
                    source_node_id="company:acme",
                    target_node_id="metric:rev-2020",
                    document_id="doc-1",
                    properties={"period_year": 2020},
                ),
                KnowledgeGraphRelationship(
                    relationship_id="rel:has_risk",
                    relationship_type="HAS_RISK",
                    source_node_id="company:acme",
                    target_node_id="risk:market",
                    document_id="doc-1",
                ),
            ],
        )
    )

    paths = graph_store.search("ACME", document_id="doc-1", year=2021, limit=10)
    assert paths
    assert any(any(node.node_id == "risk:market" for node in path.nodes) for path in paths)
    assert not any(
        {node.node_id for node in path.nodes} == {"company:acme", "metric:rev-2020"}
        for path in paths
    )


def test_graph_search_section_hint_falls_back_when_unmatched(tmp_path: Path) -> None:
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
                    node_id="risk:market",
                    node_type="risk",
                    name="market_risk",
                    document_id="doc-1",
                ),
            ],
            relationships=[
                KnowledgeGraphRelationship(
                    relationship_id="rel:has_risk",
                    relationship_type="HAS_RISK",
                    source_node_id="company:acme",
                    target_node_id="risk:market",
                    document_id="doc-1",
                ),
            ],
        )
    )

    unfiltered = graph_store.search("市场风险", document_id="doc-1", limit=5)
    hinted = graph_store.search(
        "市场风险",
        document_id="doc-1",
        section_hint="risk_section",
        limit=5,
    )
    assert unfiltered
    assert {path.path_id for path in hinted} == {path.path_id for path in unfiltered}


def test_graph_search_uses_chinese_subterms_to_rank_specific_risk(
    tmp_path: Path,
) -> None:
    graph_store = LocalKnowledgeGraphStore(str(tmp_path / "graph"))
    graph_store.replace_document(
        DocumentKnowledgeGraph(
            document_id="doc-1",
            company_id="acme",
            nodes=[
                KnowledgeGraphNode(
                    node_id="company:acme",
                    node_type="company",
                    name="示例公司",
                ),
                KnowledgeGraphNode(
                    node_id="risk:market",
                    node_type="risk",
                    name="市场价格波动风险",
                    document_id="doc-1",
                ),
                KnowledgeGraphNode(
                    node_id="risk:supply-chain",
                    node_type="risk",
                    name="供应链中断风险",
                    document_id="doc-1",
                ),
            ],
            relationships=[
                KnowledgeGraphRelationship(
                    relationship_id="rel:a-market",
                    relationship_type="HAS_RISK",
                    source_node_id="company:acme",
                    target_node_id="risk:market",
                    document_id="doc-1",
                ),
                KnowledgeGraphRelationship(
                    relationship_id="rel:z-supply-chain",
                    relationship_type="HAS_RISK",
                    source_node_id="company:acme",
                    target_node_id="risk:supply-chain",
                    document_id="doc-1",
                ),
            ],
        )
    )

    paths = graph_store.search(
        "供应链风险如何影响公司？",
        document_id="doc-1",
        limit=2,
    )

    assert paths
    assert paths[0].nodes[-1].node_id == "risk:supply-chain"
    assert paths[0].score > paths[1].score


def test_graph_search_prefers_reported_metric_relation_over_document_evidence(
    tmp_path: Path,
) -> None:
    graph_store = LocalKnowledgeGraphStore(str(tmp_path / "graph"))
    graph_store.replace_document(
        DocumentKnowledgeGraph(
            document_id="doc-1",
            company_id="acme",
            nodes=[
                KnowledgeGraphNode(
                    node_id="company:acme",
                    node_type="company",
                    name="示例公司",
                ),
                KnowledgeGraphNode(
                    node_id="metric:revenue",
                    node_type="metric",
                    name="营业收入",
                    document_id="doc-1",
                ),
                KnowledgeGraphNode(
                    node_id="document:annual-report",
                    node_type="document",
                    name="示例公司财务报告",
                    document_id="doc-1",
                ),
            ],
            relationships=[
                KnowledgeGraphRelationship(
                    relationship_id="rel:reports",
                    relationship_type="REPORTS_METRIC",
                    source_node_id="company:acme",
                    target_node_id="metric:revenue",
                    document_id="doc-1",
                ),
                KnowledgeGraphRelationship(
                    relationship_id="rel:evidence",
                    relationship_type="EVIDENCED_BY",
                    source_node_id="metric:revenue",
                    target_node_id="document:annual-report",
                    document_id="doc-1",
                ),
            ],
        )
    )

    paths = graph_store.search(
        "公司报告了哪些财务指标关联？",
        document_id="doc-1",
        limit=2,
    )

    assert paths
    assert paths[0].relationships[0].relationship_type == "REPORTS_METRIC"
