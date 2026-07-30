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
