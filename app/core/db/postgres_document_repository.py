from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db.postgres_mappers import document_record_from_orm, document_record_to_orm
from app.core.db.postgres_models import DocumentORM
from app.core.errors import DocumentNotFoundError
from src.claude_copilot.schemas.document import DocumentProcessingStatus, DocumentRecord


class PostgresDocumentRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list(self) -> list[DocumentRecord]:
        with self._session_factory() as session:
            rows = session.execute(select(DocumentORM).order_by(DocumentORM.created_at)).scalars().all()
            return [document_record_from_orm(row) for row in rows]

    def get(self, doc_id: str) -> DocumentRecord:
        with self._session_factory() as session:
            row = session.get(DocumentORM, doc_id)
            if row is None:
                raise DocumentNotFoundError(f"Document not found: {doc_id}")
            return document_record_from_orm(row)

    def save(self, record: DocumentRecord) -> DocumentRecord:
        with self._session_factory() as session:
            row = document_record_to_orm(record)
            session.merge(row)
            session.commit()
        return record

    def update_status(
        self,
        doc_id: str,
        status: DocumentProcessingStatus,
        *,
        parsed_path: str | None = None,
        segment_count: int | None = None,
        error_message: str | None = None,
    ) -> DocumentRecord:
        record = self.get(doc_id)
        record.status = status
        record.updated_at = datetime.utcnow()
        if parsed_path is not None:
            record.parsed_path = parsed_path
        if segment_count is not None:
            record.segment_count = segment_count
        record.error_message = error_message
        return self.save(record)
