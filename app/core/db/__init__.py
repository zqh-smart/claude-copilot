"""Database, vector store, and persistence adapters."""

from app.core.db.document_repository import LocalDocumentRepository
from app.core.db.financial_data_repository import (
    LocalFinancialDataRepository,
    PostgresFinancialDataRepository,
    build_company_id,
)
from app.core.db.parsed_document_repository import (
    LocalParsedDocumentRepository,
    PostgresParsedDocumentRepository,
)
from app.core.db.postgres_document_repository import PostgresDocumentRepository
from app.core.db.postgres_segment_repository import PostgresSegmentRepository
from app.core.db.protocols import (
    DocumentRepositoryProtocol,
    FinancialDataRepositoryProtocol,
    ParsedDocumentRepositoryProtocol,
    SegmentRepositoryProtocol,
)
from app.core.db.segment_repository import LocalSegmentRepository
from app.core.db.serving_facts import select_serving_metric_facts, select_serving_metric_facts_from_document
from app.core.db.session import get_postgres_engine, get_postgres_session_factory

__all__ = [
    "DocumentRepositoryProtocol",
    "FinancialDataRepositoryProtocol",
    "SegmentRepositoryProtocol",
    "ParsedDocumentRepositoryProtocol",
    "LocalDocumentRepository",
    "LocalSegmentRepository",
    "LocalParsedDocumentRepository",
    "PostgresDocumentRepository",
    "PostgresSegmentRepository",
    "PostgresParsedDocumentRepository",
    "LocalFinancialDataRepository",
    "PostgresFinancialDataRepository",
    "build_company_id",
    "get_postgres_engine",
    "get_postgres_session_factory",
    "select_serving_metric_facts",
    "select_serving_metric_facts_from_document",
]
