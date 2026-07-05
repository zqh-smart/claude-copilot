from app.core.kg import KnowledgeGraphBuilder, LocalKnowledgeGraphStore
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    FinancialMetricFact,
    FinancialSchema,
    ParsedDocument,
    SemanticSectionSchema,
)
from src.claude_copilot.schemas.knowledge_graph import DocumentKnowledgeGraph


def test_build_store_and_query_document_knowledge_graph(tmp_path) -> None:
    document = ParsedDocument(
        doc_id="doc-1",
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="test",
            filename="report.txt",
            company="ACME",
            year=2025,
        ),
        financial_schema=FinancialSchema(
            company="ACME",
            year=2025,
            metric_facts=[
                FinancialMetricFact(
                    metric_key="revenue",
                    period="2025",
                    value=125,
                    unit="million",
                    currency="USD",
                )
            ],
            semantic_sections=[
                SemanticSectionSchema(
                    section_id="risk-1",
                    section_type="risk_section",
                    title="Risk factors",
                    evidence_text="Liquidity pressure and market volatility remain key risks.",
                    page_range=(4, 5),
                )
            ],
        ),
    )

    graph = KnowledgeGraphBuilder().build(document)
    store = LocalKnowledgeGraphStore(str(tmp_path))
    store.replace_document(graph)

    restored = store.get_document("doc-1")
    assert {node.node_type for node in restored.nodes} == {
        "company",
        "document",
        "metric",
        "risk",
    }
    assert {item.relationship_type for item in restored.relationships} >= {
        "HAS_DOCUMENT",
        "REPORTS_METRIC",
        "HAS_RISK",
        "EVIDENCED_BY",
    }

    risk_paths = store.search(
        "What liquidity risks affect the company?",
        document_id="doc-1",
        company_id=graph.company_id,
    )
    assert risk_paths
    assert any(
        relationship.relationship_type == "HAS_RISK"
        for path in risk_paths
        for relationship in path.relationships
    )


def test_replacing_document_graph_is_idempotent(tmp_path) -> None:
    graph = DocumentKnowledgeGraph(document_id="doc-1")
    store = LocalKnowledgeGraphStore(str(tmp_path))

    store.replace_document(graph)
    store.replace_document(graph)

    assert store.get_document("doc-1") == graph
