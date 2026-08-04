from functools import lru_cache

from qdrant_client import QdrantClient

from app.api.services.document_service import DocumentService
from app.api.services.financial_data_service import FinancialDataService
from app.api.services.ingestion_job_service import IngestionJobService
from app.api.services.research_service import ResearchService
from app.core.chat_memory import ChatMemoryProtocol, HttpChatMemoryClient, NoopChatMemory
from app.core.config import get_settings
from app.core.db import (
    LocalDocumentRepository,
    LocalFinancialDataRepository,
    LocalIngestionJobRepository,
    LocalParsedDocumentRepository,
    LocalSegmentRepository,
    PostgresDocumentRepository,
    PostgresFinancialDataRepository,
    PostgresIngestionJobRepository,
    PostgresParsedDocumentRepository,
    PostgresSegmentRepository,
    get_postgres_session_factory,
)
from app.core.kg import (
    LocalKnowledgeGraphStore,
    Neo4jKnowledgeGraphStore,
    NoOpKnowledgeGraphStore,
)
from app.core.llm import GroundedResearchEngine, build_json_chat_client
from app.core.observability import build_observability
from app.core.rag import (
    LocalRetriever,
    NoOpVectorStore,
    QdrantVectorStore,
    RetrievalOrchestrator,
    build_embedding_service,
    build_reranking_service,
)
from app.core.storage import LocalFileStorage
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService


@lru_cache
def get_document_repository():
    settings = get_settings()
    if settings.storage_backend == "postgres":
        return PostgresDocumentRepository(get_postgres_session_factory())
    return LocalDocumentRepository(settings.parsed_data_path)


@lru_cache
def get_segment_repository():
    settings = get_settings()
    if settings.storage_backend == "postgres":
        return PostgresSegmentRepository(get_postgres_session_factory())
    return LocalSegmentRepository(settings.parsed_data_path)


@lru_cache
def get_parsed_document_repository():
    settings = get_settings()
    if settings.storage_backend == "postgres":
        return PostgresParsedDocumentRepository(get_postgres_session_factory())
    return LocalParsedDocumentRepository(settings.parsed_data_path)


@lru_cache
def get_financial_data_repository():
    settings = get_settings()
    if settings.storage_backend == "postgres":
        return PostgresFinancialDataRepository(get_postgres_session_factory())
    return LocalFinancialDataRepository(
        get_document_repository(),
        get_parsed_document_repository(),
    )


@lru_cache
def get_ingestion_job_repository():
    settings = get_settings()
    if settings.storage_backend == "postgres":
        return PostgresIngestionJobRepository(get_postgres_session_factory())
    return LocalIngestionJobRepository(settings.parsed_data_path)


@lru_cache
def get_embedding_service():
    return build_embedding_service(get_settings())


@lru_cache
def get_qdrant_client():
    settings = get_settings()
    return QdrantClient(
        url=settings.qdrant_url,
        grpc_port=settings.qdrant_grpc_port,
        prefer_grpc=True,
        api_key=settings.qdrant_api_key or None,
        check_compatibility=False,
        timeout=15,
    )


@lru_cache
def get_vector_store():
    settings = get_settings()
    if settings.vector_store_backend == "none":
        return NoOpVectorStore()
    return QdrantVectorStore(
        client=get_qdrant_client(),
        collection_name=settings.qdrant_collection_name,
        embedding_service=get_embedding_service(),
    )


@lru_cache
def get_graph_store():
    settings = get_settings()
    if settings.graph_store_backend == "none":
        return NoOpKnowledgeGraphStore()
    if settings.graph_store_backend == "neo4j":
        return Neo4jKnowledgeGraphStore(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )
    return LocalKnowledgeGraphStore(settings.graph_data_path)


@lru_cache
def get_reranking_service():
    return build_reranking_service(get_settings())


@lru_cache
def get_json_chat_client():
    return build_json_chat_client(get_settings())


@lru_cache
def get_grounded_research_engine():
    settings = get_settings()
    if not settings.llm_grounded_synthesis_enabled:
        return None
    return GroundedResearchEngine(get_json_chat_client())


@lru_cache
def get_observability():
    return build_observability(get_settings())


@lru_cache
def get_document_pipeline_service() -> DocumentPipelineService:
    settings = get_settings()
    return DocumentPipelineService(
        document_repository=get_document_repository(),
        segment_repository=get_segment_repository(),
        storage=LocalFileStorage(),
        document_storage_path=settings.document_storage_path,
        raw_data_path=settings.raw_data_path,
        parsed_data_path=settings.parsed_data_path,
        parsed_document_repository=get_parsed_document_repository(),
        vector_store=get_vector_store(),
        graph_store=get_graph_store(),
    )


@lru_cache
def get_document_service() -> DocumentService:
    return DocumentService(get_document_pipeline_service())


@lru_cache
def get_ingestion_job_service() -> IngestionJobService:
    settings = get_settings()
    service = IngestionJobService(
        pipeline_service=get_document_pipeline_service(),
        repository=get_ingestion_job_repository(),
        worker_count=settings.ingestion_worker_count,
        default_max_attempts=settings.ingestion_max_attempts,
        retry_delay_seconds=settings.ingestion_retry_delay_seconds,
        lease_seconds=settings.ingestion_lease_seconds,
        heartbeat_seconds=settings.ingestion_heartbeat_seconds,
        worker_id=settings.ingestion_worker_id,
        inline_execution_enabled=settings.ingestion_inline_execution_enabled,
        alert_oldest_ready_seconds=settings.ingestion_alert_oldest_ready_seconds,
        alert_retry_wait_count=settings.ingestion_alert_retry_wait_count,
        alert_recent_failure_count=settings.ingestion_alert_recent_failure_count,
        alert_failure_window_seconds=settings.ingestion_alert_failure_window_seconds,
    )
    if settings.ingestion_recover_on_startup and settings.ingestion_inline_execution_enabled:
        service.recover_incomplete()
    return service


@lru_cache
def get_financial_data_service() -> FinancialDataService:
    return FinancialDataService(get_financial_data_repository())


@lru_cache
def get_chat_memory_client() -> ChatMemoryProtocol:
    settings = get_settings()
    if not settings.chat_memory_enabled:
        return NoopChatMemory(reason="chat_memory_disabled")
    return HttpChatMemoryClient(settings=settings)


@lru_cache
def get_research_service() -> ResearchService:
    settings = get_settings()
    pipeline_service = get_document_pipeline_service()
    retriever = LocalRetriever(
        get_segment_repository(),
        vector_store=get_vector_store(),
        reranker=get_reranking_service(),
        candidate_multiplier=settings.retrieval_candidate_multiplier,
        vector_weight=settings.hybrid_vector_weight,
        lexical_weight=settings.hybrid_lexical_weight,
    )
    return ResearchService(
        document_pipeline_service=pipeline_service,
        retriever=retriever,
        orchestrator=RetrievalOrchestrator(
            vector_retriever=retriever,
            financial_repository=get_financial_data_repository(),
            graph_store=get_graph_store(),
        ),
        grounded_engine=get_grounded_research_engine(),
        observability=get_observability(),
        capture_trace_content=settings.observability_capture_content,
        max_revisions=settings.llm_max_revisions,
    )
