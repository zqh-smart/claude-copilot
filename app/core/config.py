from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Claude Copilot"
    app_env: str = "development"
    app_debug: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # LLM chat（与 .env 中 LLM_MODEL_* 对齐）
    llm_model_name: str = "qwen3.5"
    llm_model_base_url: str = "http://192.168.0.102:30000/v1"
    llm_model_api_key: str | None = None
    llm_model_api_type: Literal["openai", "silicon"] = "openai"
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

    langsmith_tracing: bool = True
    langsmith_api_key: str | None = None
    langsmith_project: str = "claude-copilot"

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://localhost:3000"

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
