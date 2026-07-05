from __future__ import annotations

import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db.postgres_mappers import document_segment_from_orm, document_segment_to_orm
from app.core.db.postgres_models import DocumentSegmentORM
from src.claude_copilot.schemas.document import DocumentSegment


class PostgresSegmentRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def replace_for_document(self, doc_id: str, segments: list[DocumentSegment]) -> None:
        with self._session_factory() as session:
            session.execute(delete(DocumentSegmentORM).where(DocumentSegmentORM.doc_id == doc_id))
            session.add_all(document_segment_to_orm(segment) for segment in segments)
            session.commit()

    def list_for_document(self, doc_id: str) -> list[DocumentSegment]:
        with self._session_factory() as session:
            rows = session.execute(
                select(DocumentSegmentORM)
                .where(DocumentSegmentORM.doc_id == doc_id)
                .order_by(DocumentSegmentORM.position)
            ).scalars().all()
            return [document_segment_from_orm(row) for row in rows]

    def search(
        self,
        query: str,
        *,
        doc_id: str | None = None,
        top_k: int = 3,
    ) -> list[tuple[DocumentSegment, float]]:
        with self._session_factory() as session:
            stmt = select(DocumentSegmentORM)
            if doc_id is not None:
                stmt = stmt.where(DocumentSegmentORM.doc_id == doc_id)
            rows = session.execute(stmt).scalars().all()

        tokens = self._tokenize(query)
        scored: list[tuple[DocumentSegment, float]] = []
        for row in rows:
            segment = document_segment_from_orm(row)
            score = self._score(tokens, segment.content)
            if score > 0:
                scored.append((segment, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token for token in re.split(r"\W+", text.lower()) if token}

    def _score(self, query_tokens: set[str], content: str) -> float:
        if not query_tokens:
            return 0.0
        content_tokens = self._tokenize(content)
        if not content_tokens:
            return 0.0
        overlap = query_tokens.intersection(content_tokens)
        return len(overlap) / len(query_tokens)
