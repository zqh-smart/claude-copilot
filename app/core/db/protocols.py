from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.claude_copilot.schemas.document import DocumentRecord, DocumentSegment, ParsedDocument
from src.claude_copilot.schemas.financial_data import CompanySummary, FinancialMetricObservation
from src.claude_copilot.schemas.ingestion import IngestionJob


class DocumentRepositoryProtocol(Protocol):
    def list(self) -> list[DocumentRecord]:
        ...

    def get(self, doc_id: str) -> DocumentRecord:
        ...

    def save(self, record: DocumentRecord) -> DocumentRecord:
        ...

    def update_status(
        self,
        doc_id: str,
        status,
        *,
        parsed_path: str | None = None,
        segment_count: int | None = None,
        error_message: str | None = None,
    ) -> DocumentRecord:
        ...


class SegmentRepositoryProtocol(Protocol):
    def replace_for_document(self, doc_id: str, segments: list[DocumentSegment]) -> None:
        ...

    def list_for_document(self, doc_id: str) -> list[DocumentSegment]:
        ...

    def search(
        self,
        query: str,
        *,
        doc_id: str | None = None,
        top_k: int = 3,
    ) -> list[tuple[DocumentSegment, float]]:
        ...


class ParsedDocumentRepositoryProtocol(Protocol):
    def save(self, parsed_document: ParsedDocument) -> str:
        ...

    def get(self, doc_id: str) -> ParsedDocument:
        ...


class IngestionJobRepositoryProtocol(Protocol):
    def list(self, *, limit: int = 100) -> list[IngestionJob]:
        ...

    def get(self, job_id: str) -> IngestionJob:
        ...

    def save(self, job: IngestionJob) -> IngestionJob:
        ...

    def claim(
        self,
        job_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> IngestionJob | None:
        ...

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> bool:
        ...

    def save_owned(self, job: IngestionJob, *, worker_id: str) -> IngestionJob | None:
        ...

    def request_cancel(self, job_id: str, *, now: datetime) -> IngestionJob | None:
        ...


class FinancialDataRepositoryProtocol(Protocol):
    def list_companies(self) -> list[CompanySummary]:
        ...

    def get_company(self, company_id: str) -> CompanySummary | None:
        ...

    def query_metrics(
        self,
        company_id: str,
        *,
        year: int | None = None,
        metric_key: str | None = None,
        statement_type: str | None = None,
        document_id: str | None = None,
        limit: int = 500,
    ) -> list[FinancialMetricObservation]:
        ...
