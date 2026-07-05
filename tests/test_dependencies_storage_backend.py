from types import SimpleNamespace

from app.api import dependencies
from app.core.db import (
    LocalDocumentRepository,
    LocalParsedDocumentRepository,
    LocalSegmentRepository,
    PostgresDocumentRepository,
    PostgresParsedDocumentRepository,
    PostgresSegmentRepository,
)
from app.core.rag import NoOpVectorStore


def clear_dependency_caches() -> None:
    dependencies.get_document_repository.cache_clear()
    dependencies.get_segment_repository.cache_clear()
    dependencies.get_parsed_document_repository.cache_clear()
    dependencies.get_embedding_service.cache_clear()
    dependencies.get_qdrant_client.cache_clear()
    dependencies.get_vector_store.cache_clear()
    dependencies.get_reranking_service.cache_clear()
    dependencies.get_document_pipeline_service.cache_clear()
    dependencies.get_document_service.cache_clear()
    dependencies.get_research_service.cache_clear()


def test_local_storage_backend_uses_local_repositories(monkeypatch, tmp_path) -> None:
    settings = SimpleNamespace(
        storage_backend="local",
        parsed_data_path=str(tmp_path / "parsed"),
        document_storage_path=str(tmp_path / "documents"),
        raw_data_path=str(tmp_path / "raw"),
        embedding_backend="hash",
        embedding_model_id="BAAI/bge-m3",
        embedding_dimensions=64,
        rerank_backend="deterministic",
        rerank_model_id="BAAI/bge-reranker-v2-m3",
        hybrid_vector_weight=0.65,
        hybrid_lexical_weight=0.35,
        retrieval_candidate_multiplier=4,
        silicon_base_url="https://api.siliconflow.cn/v1",
        silicon_key=None,
        qdrant_url="http://localhost:6333",
        qdrant_api_key=None,
        qdrant_grpc_port=6334,
        qdrant_collection_name="test_segments",
        vector_store_backend="none",
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    clear_dependency_caches()

    assert isinstance(dependencies.get_document_repository(), LocalDocumentRepository)
    assert isinstance(dependencies.get_segment_repository(), LocalSegmentRepository)
    assert isinstance(dependencies.get_parsed_document_repository(), LocalParsedDocumentRepository)
    assert isinstance(dependencies.get_vector_store(), NoOpVectorStore)

    clear_dependency_caches()


def test_postgres_storage_backend_uses_postgres_repositories(monkeypatch, tmp_path) -> None:
    settings = SimpleNamespace(
        storage_backend="postgres",
        parsed_data_path=str(tmp_path / "parsed"),
        document_storage_path=str(tmp_path / "documents"),
        raw_data_path=str(tmp_path / "raw"),
        embedding_backend="hash",
        embedding_model_id="BAAI/bge-m3",
        embedding_dimensions=64,
        rerank_backend="deterministic",
        rerank_model_id="BAAI/bge-reranker-v2-m3",
        hybrid_vector_weight=0.65,
        hybrid_lexical_weight=0.35,
        retrieval_candidate_multiplier=4,
        silicon_base_url="https://api.siliconflow.cn/v1",
        silicon_key=None,
        qdrant_url="http://localhost:6333",
        qdrant_api_key=None,
        qdrant_grpc_port=6334,
        qdrant_collection_name="test_segments",
        vector_store_backend="none",
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    monkeypatch.setattr(dependencies, "get_postgres_session_factory", lambda: object())
    clear_dependency_caches()

    assert isinstance(dependencies.get_document_repository(), PostgresDocumentRepository)
    assert isinstance(dependencies.get_segment_repository(), PostgresSegmentRepository)
    assert isinstance(dependencies.get_parsed_document_repository(), PostgresParsedDocumentRepository)

    clear_dependency_caches()
