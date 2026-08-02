from app.core.kg import (
    KnowledgeGraphBuilder,
    LocalKnowledgeGraphStore,
    evaluate_document_graph,
)
from src.claude_copilot.entity_resolution import EntityResolver
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    FinancialMetricFact,
    FinancialSchema,
    ParsedDocument,
    ParsedSection,
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


def test_extracts_business_entities_with_relationship_provenance(tmp_path) -> None:
    document = ParsedDocument(
        doc_id="annual-2025",
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="test",
            filename="annual-report.txt",
            company="ACME Holdings, Inc.",
            company_aliases=["ACME"],
            year=2025,
        ),
        sections=[
            ParsedSection(
                title="Business overview",
                page_start=7,
                page_end=8,
                content=(
                    "ACME Finance is a wholly-owned subsidiary. "
                    "The company has three reportable business segments – Consumer Banking, "
                    "Commercial Banking, and Asset Management. "
                    "Competitors include Beta Bank and Gamma Financial. "
                    "ACME operates banking, lending and deposit services. "
                    "In 2025 ACME acquired Delta Payments to expand its offering."
                ),
            )
        ],
    )

    graph = KnowledgeGraphBuilder().build(document)
    node_types = {node.node_type for node in graph.nodes}
    relationship_types = {item.relationship_type for item in graph.relationships}

    assert {"company", "subsidiary", "industry", "business_segment", "event"} <= node_types
    assert {"OWNS", "OPERATES_IN", "AFFECTED_BY", "COMPETES_WITH"} <= relationship_types
    business_relationships = [
        item
        for item in graph.relationships
        if item.relationship_type in {"OWNS", "OPERATES_IN", "AFFECTED_BY", "COMPETES_WITH"}
    ]
    assert business_relationships
    assert all(
        item.page_range == (7, 8) or item.relationship_type == "OPERATES_IN"
        for item in business_relationships
    )
    assert all(item.evidence_text for item in business_relationships)
    assert all(0 < item.confidence <= 1 for item in business_relationships)


def test_company_identity_and_graph_merge_across_years(tmp_path) -> None:
    builder = KnowledgeGraphBuilder()
    first = ParsedDocument(
        doc_id="annual-2023",
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="test",
            company="JPMorgan Chase & Co.",
            year=2023,
        ),
    )
    second = ParsedDocument(
        doc_id="annual-2024",
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="test",
            company="JPMorganChase",
            year=2024,
        ),
    )
    first_graph = builder.build(first)
    second_graph = builder.build(second)
    store = LocalKnowledgeGraphStore(str(tmp_path))
    store.replace_document(first_graph)
    store.replace_document(second_graph)

    assert first_graph.company_id == second_graph.company_id
    merged = store.get_company(first_graph.company_id)
    company_nodes = [
        node
        for node in merged.nodes
        if node.node_type == "company" and node.properties["company_id"] == first_graph.company_id
    ]
    assert len(company_nodes) == 1
    assert merged.document_ids == ["annual-2023", "annual-2024"]
    assert merged.years == [2023, 2024]

    resolver = EntityResolver()
    assert (
        resolver.resolve_company(
            "JPMC",
            aliases=["JPMorgan Chase & Co."],
        ).entity_id
        == first_graph.company_id
    )


def test_chinese_legal_suffix_aliases_resolve_to_one_company() -> None:
    resolver = EntityResolver()

    assert resolver.resolve_company("北京指南针科技发展股份有限公司").entity_id == (
        resolver.resolve_company("北京指南针科技发展有限公司").entity_id
    )
    assert resolver.canonical_key("苏州天华新能源科技有限责任公司") == (
        "苏州天华新能源科技"
    )
    assert resolver.resolve_company(
        "聚灿光电科技股份有限公司",
        aliases=["指南针", "300803"],
    ).canonical_key == "聚灿光电科技"


def test_graph_quality_requires_complete_relationship_provenance() -> None:
    document = ParsedDocument(
        doc_id="quality-doc",
        metadata=DocumentMetadata(
            doc_type="annual_report",
            source="test",
            filename="quality.pdf",
            company="Quality Co., Ltd.",
            year=2025,
            page_count=20,
        ),
        financial_schema=FinancialSchema(
            company="Quality Co., Ltd.",
            metric_facts=[
                FinancialMetricFact(
                    metric_key="revenue",
                    period="2025",
                    value=100,
                    source_table_id="income",
                    page_range=(8, 8),
                )
            ],
        ),
    )

    report = evaluate_document_graph(KnowledgeGraphBuilder().build(document))

    assert report.passed is True
    assert report.missing_endpoint_count == 0
    assert report.missing_evidence_count == 0
    assert report.evidence_grounding_rate == 1.0
