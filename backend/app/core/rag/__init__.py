"""RAG-related core modules.

This package is intentionally named after the Bank-copilot-main structure so that
query expansion, reranking, retrieval orchestration, and metadata filtering can be
introduced incrementally without reshaping the project later.
"""

from app.core.rag.embeddings import (
    EmbeddingServiceProtocol,
    HashEmbeddingService,
    SiliconEmbeddingService,
    build_embedding_service,
)
from app.core.rag.orchestrator import QueryAnalyzer, RetrievalOrchestrator
from app.core.rag.query_expansion import QueryExpansionService
from app.core.rag.reranking import (
    DeterministicRerankingService,
    RerankingServiceProtocol,
    SiliconRerankingService,
    build_reranking_service,
)
from app.core.rag.retriever import LocalRetriever
from app.core.rag.vector_store import NoOpVectorStore, QdrantVectorStore, VectorStoreProtocol

__all__ = [
    "build_reranking_service",
    "EmbeddingServiceProtocol",
    "DeterministicRerankingService",
    "HashEmbeddingService",
    "LocalRetriever",
    "NoOpVectorStore",
    "QdrantVectorStore",
    "QueryExpansionService",
    "QueryAnalyzer",
    "RetrievalOrchestrator",
    "RerankingServiceProtocol",
    "SiliconEmbeddingService",
    "SiliconRerankingService",
    "VectorStoreProtocol",
    "build_embedding_service",
]
