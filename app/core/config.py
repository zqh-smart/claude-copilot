from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Claude Copilot"
    app_env: str = "development"
    app_debug: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Agent Chat UI → LangGraph `agent` graph (optional default Serving doc)
    agent_chat_doc_id: str | None = None
    agent_chat_doc_id_b: str | None = None

    # Chat memory (MemoryCore sidecar) — conversation L0–L3 only; not document KG
    chat_memory_enabled: bool = False
    chat_memory_base_url: str = "http://127.0.0.1:8420"
    chat_memory_api_key: str | None = None
    chat_memory_service_id: str = "claude-copilot-local"
    chat_memory_team_id: str = "default-team"
    chat_memory_agent_id: str = "agent"
    chat_memory_user_id: str = "local-user"
    chat_memory_recall_timeout_ms: int = 5000
    chat_memory_recall_max_results: int = 5
    chat_memory_capture_enabled: bool = True
    chat_memory_max_chars_per_memory: int = 400
    chat_memory_max_total_recall_chars: int = 2000
    # Same dir as TDAI_DATA_DIR / run_memory_core.ps1 (local jsonl browse for Workbench)
    chat_memory_data_dir: str = "data/chat_memory"

    # LLM chat（与 .env 中 LLM_MODEL_* 对齐）
    llm_model_name: str = "qwen3.5"
    llm_model_base_url: str = "http://192.168.0.102:30000/v1"
    llm_model_api_key: str | None = None
    llm_model_api_type: Literal["openai", "silicon", "bailian"] = "openai"
    llm_grounded_synthesis_enabled: bool = True
    llm_temperature: float = 0.1
    llm_timeout_seconds: float = 90.0
    llm_max_revisions: int = 1

    # Embedding / Rerank（硅基等；与 LLM chat 配置分离）
    default_embedding_model: str = "BAAI/bge-m3"
    embedding_backend: Literal["auto", "silicon", "hash"] = "auto"
    embedding_model_id: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    rerank_backend: Literal["auto", "silicon", "deterministic"] = "auto"
    rerank_model_id: str = "BAAI/bge-reranker-v2-m3"
    hybrid_vector_weight: float = 0.65
    hybrid_lexical_weight: float = 0.35
    retrieval_candidate_multiplier: int = 4
    silicon_base_url: str = "https://api.siliconflow.cn/v1"
    silicon_key: str | None = None
    bailian_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "BAI_LIAN_API_KEY",
            "BAILIAN_API_KEY",
            "DASHSCOPE_API_KEY",
        ),
    )
    bailian_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bailian_fallback_models: str = "qwen3.7-plus,qwen3.7-flash"

    postgres_dsn: str = "postgresql+psycopg://postgres:postgres@localhost:5432/claude_copilot"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_grpc_port: int = 6334
    qdrant_collection_name: str = "document_segments_bge_m3"
    vector_store_backend: Literal["none", "qdrant"] = "qdrant"
    graph_store_backend: Literal["none", "local", "neo4j"] = "local"
    graph_data_path: str = "./data/graph"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "claude-copilot"
    neo4j_database: str = "neo4j"
    redis_url: str = "redis://localhost:6379/0"
    ingestion_worker_count: int = 2
    ingestion_max_attempts: int = 3
    ingestion_retry_delay_seconds: float = 2.0
    ingestion_recover_on_startup: bool = True
    ingestion_inline_execution_enabled: bool = False
    ingestion_worker_id: str | None = None
    ingestion_lease_seconds: float = 120.0
    ingestion_heartbeat_seconds: float = 30.0
    ingestion_alert_oldest_ready_seconds: float = 300.0
    ingestion_alert_retry_wait_count: int = 5
    ingestion_alert_recent_failure_count: int = 1
    ingestion_alert_failure_window_seconds: float = 3600.0

    langsmith_tracing: bool = True
    langsmith_api_key: str | None = None
    langsmith_project: str = "claude-copilot"

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
    )
    observability_capture_content: bool = False

    feature_pipeline_enabled: bool = False
    storage_backend: Literal["local", "postgres"] = "local"
    document_storage_path: str = "./data/documents"
    raw_data_path: str = "./data/raw"
    parsed_data_path: str = "./data/parsed"
    report_data_path: str = "./data/reports"
    pdf_parser_backend_priority: str = "mineru_pdf,table_pdf,native_pdf,ocr_pdf"
    markdown_split_by_headers: bool = True
    docx_extract_tables: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
