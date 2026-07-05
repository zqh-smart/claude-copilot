from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db.postgres_mappers import (
    metric_fact_to_orm,
    note_fact_to_orm,
    parsed_document_from_payload,
    parsed_table_to_orm,
)
from app.core.db.postgres_models import FinancialItemORM, ParsedDocumentORM, ParsedTableORM
from app.core.errors import DocumentNotFoundError
from app.core.storage import LocalFileStorage
from src.claude_copilot.schemas.document import ParsedDocument


class LocalParsedDocumentRepository:
    def __init__(self, base_dir: str, storage: LocalFileStorage | None = None) -> None:
        self._base_dir = Path(base_dir)
        self._storage = storage or LocalFileStorage()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, parsed_document: ParsedDocument) -> str:
        target = self._base_dir / f"{parsed_document.doc_id}.json"
        self._storage.save_text(
            target,
            json.dumps(parsed_document.model_dump(mode="json"), ensure_ascii=False, indent=2),
        )
        return str(target)

    def get(self, doc_id: str) -> ParsedDocument:
        target = self._base_dir / f"{doc_id}.json"
        if not target.exists():
            raise DocumentNotFoundError(f"Parsed document not found: {doc_id}")
        payload = json.loads(target.read_text(encoding="utf-8"))
        return ParsedDocument.model_validate(payload)


class PostgresParsedDocumentRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, parsed_document: ParsedDocument) -> str:
        payload = parsed_document.model_dump(mode="json")
        with self._session_factory() as session:
            session.merge(
                ParsedDocumentORM(
                    doc_id=parsed_document.doc_id,
                    payload=payload,
                )
            )
            session.execute(delete(ParsedTableORM).where(ParsedTableORM.doc_id == parsed_document.doc_id))
            session.execute(delete(FinancialItemORM).where(FinancialItemORM.doc_id == parsed_document.doc_id))

            session.add_all(
                parsed_table_to_orm(parsed_document.doc_id, table, table_index)
                for table_index, table in enumerate(parsed_document.tables, start=1)
            )

            if parsed_document.financial_schema is not None:
                session.add_all(
                    metric_fact_to_orm(parsed_document.doc_id, fact, fact_index)
                    for fact_index, fact in enumerate(parsed_document.financial_schema.metric_facts, start=1)
                )
                session.add_all(
                    note_fact_to_orm(parsed_document.doc_id, fact, fact_index)
                    for fact_index, fact in enumerate(parsed_document.financial_schema.note_facts, start=1)
                )

            session.commit()
        return f"postgres:parsed_documents/{parsed_document.doc_id}"

    def get(self, doc_id: str) -> ParsedDocument:
        with self._session_factory() as session:
            row = session.execute(
                select(ParsedDocumentORM).where(ParsedDocumentORM.doc_id == doc_id)
            ).scalar_one_or_none()
            if row is None:
                raise DocumentNotFoundError(f"Parsed document not found: {doc_id}")
            return parsed_document_from_payload(row.payload)
