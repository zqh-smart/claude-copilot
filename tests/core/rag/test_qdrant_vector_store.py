from qdrant_client import QdrantClient

from app.core.db import LocalSegmentRepository
from app.core.rag import HashEmbeddingService, LocalRetriever, QdrantVectorStore
from app.pipeline.feature_pipeline.indexing import IndexingService
from src.claude_copilot.schemas.document import DocumentSegment


def build_segment(doc_id: str, segment_id: str, position: int, content: str) -> DocumentSegment:
    return DocumentSegment(
        segment_id=segment_id,
        document_id=doc_id,
        parent_section_id=f"{doc_id}-section-1",
        position=position,
        content=content,
        content_summary=content,
        keywords=[],
        metadata={"content_type": "section"},
    )


def test_qdrant_vector_store_replaces_and_searches_document_segments() -> None:
    vector_store = QdrantVectorStore(
        client=QdrantClient(location=":memory:"),
        collection_name="document_segments",
        embedding_service=HashEmbeddingService(dimensions=64),
    )
    segments = [
        build_segment("doc-1", "doc-1-segment-1", 1, "Revenue grew strongly in 2025."),
        build_segment("doc-1", "doc-1-segment-2", 2, "Liquidity pressure remains a key risk factor."),
    ]

    vector_store.replace_for_document("doc-1", segments)
    hits = vector_store.search("What changed in revenue?", doc_id="doc-1", top_k=2)

    assert hits
    assert hits[0][0].segment_id == "doc-1-segment-1"
    assert hits[0][1] > 0


def test_indexing_service_upserts_segments_into_qdrant(tmp_path) -> None:
    segment_repository = LocalSegmentRepository(str(tmp_path / "parsed"))
    vector_store = QdrantVectorStore(
        client=QdrantClient(location=":memory:"),
        collection_name="document_segments",
        embedding_service=HashEmbeddingService(dimensions=64),
    )
    indexing = IndexingService(segment_repository, vector_store)

    segments = [
        build_segment("doc-2", "doc-2-segment-1", 1, "Credit losses increased in the consumer portfolio."),
        build_segment("doc-2", "doc-2-segment-2", 2, "Capital ratios remained above regulatory minimums."),
    ]

    count = indexing.index("doc-2", segments)
    hits = vector_store.search("consumer credit losses", doc_id="doc-2", top_k=2)

    assert count == 2
    assert hits
    assert hits[0][0].segment_id == "doc-2-segment-1"


def test_local_retriever_uses_qdrant_hits_before_lexical_fallback(tmp_path) -> None:
    segment_repository = LocalSegmentRepository(str(tmp_path / "parsed"))
    vector_store = QdrantVectorStore(
        client=QdrantClient(location=":memory:"),
        collection_name="document_segments",
        embedding_service=HashEmbeddingService(dimensions=64),
    )
    segments = [
        build_segment("doc-3", "doc-3-segment-1", 1, "Net interest income expanded due to higher loan yields."),
        build_segment("doc-3", "doc-3-segment-2", 2, "Operational expenses declined after branch consolidation."),
    ]
    segment_repository.replace_for_document("doc-3", segments)
    vector_store.replace_for_document("doc-3", segments)

    retriever = LocalRetriever(segment_repository, vector_store=vector_store)
    hits = retriever.retrieve("loan yield performance", doc_id="doc-3", top_k=2)

    assert hits
    assert hits[0][0].segment_id == "doc-3-segment-1"
