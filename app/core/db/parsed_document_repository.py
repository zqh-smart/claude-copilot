from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db.financial_data_repository import _restore_value, build_company_id
from app.core.db.postgres_mappers import (
    metric_fact_to_orm,
    note_fact_to_orm,
    parsed_document_from_payload,
    parsed_table_to_orm,
)
from app.core.db.postgres_models import DocumentORM, FinancialItemORM, ParsedDocumentORM, ParsedTableORM
from app.core.db.serving_facts import (
    MetricConflictCandidate,
    candidate_from_fact,
    dedupe_serving_metric_facts,
    metric_period_key,
    metric_values_conflict,
    prepare_serving_metric_facts,
    resolve_metric_conflict,
)
from app.core.errors import DocumentNotFoundError
from app.core.storage import LocalFileStorage
from src.claude_copilot.schemas.document import FinancialSchema, ParsedDocument


@dataclass(frozen=True)
class _ExistingMetricItem:
    row: FinancialItemORM
    document_year: int | None


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
        with self._session_factory() as session:
            serving_facts: list = []
            if parsed_document.financial_schema is not None:
                schema = parsed_document.financial_schema
                serving_facts, conflict_warnings = self._prepare_metric_facts_for_persist(
                    session,
                    parsed_document,
                    schema,
                )
                if conflict_warnings:
                    schema.metadata["metric_conflicts"] = conflict_warnings

            payload = parsed_document.model_dump(mode="json")
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
                schema = parsed_document.financial_schema
                session.add_all(
                    metric_fact_to_orm(parsed_document.doc_id, fact, fact_index)
                    for fact_index, fact in enumerate(serving_facts, start=1)
                )
                session.add_all(
                    note_fact_to_orm(parsed_document.doc_id, fact, fact_index)
                    for fact_index, fact in enumerate(schema.note_facts, start=1)
                )

            session.commit()
        return f"postgres:parsed_documents/{parsed_document.doc_id}"

    def _prepare_metric_facts_for_persist(
        self,
        session: Session,
        parsed_document: ParsedDocument,
        schema: FinancialSchema,
    ) -> tuple[list, list[str]]:
        serving_facts = dedupe_serving_metric_facts(
            prepare_serving_metric_facts(schema),
            schema=schema,
        )
        company = parsed_document.metadata.company or schema.company or ""
        company_id = build_company_id(company)
        if not company_id:
            return serving_facts, []

        existing_items = self._load_company_metric_items(
            session,
            company_id=company_id,
            exclude_doc_id=parsed_document.doc_id,
        )
        facts_to_persist: list = []
        warnings: list[str] = []
        superseded_ids: list[str] = []
        document_year = parsed_document.metadata.year or schema.year

        for fact in serving_facts:
            period_key = metric_period_key(fact.metric_key, fact.period)
            conflicting_rows = [
                item
                for item in existing_items.get(period_key, [])
                if metric_values_conflict(_existing_metric_value(item.row), fact.value)
            ]
            if not conflicting_rows:
                facts_to_persist.append(fact)
                continue

            candidates = [
                candidate_from_fact(
                    fact,
                    document_id=parsed_document.doc_id,
                    document_year=document_year,
                    schema=schema,
                )
            ]
            for item in conflicting_rows:
                row = item.row
                candidates.append(
                    MetricConflictCandidate(
                        value=_existing_metric_value(row),
                        document_id=row.doc_id,
                        document_year=item.document_year,
                        has_provenance=bool(
                            row.source_table_id
                            or row.page_range
                            or row.source_section
                            or row.provenance
                        ),
                        is_grounded=bool((row.provenance or {}).get("source_grounded")),
                    )
                )

            resolution = resolve_metric_conflict(
                candidates,
                metric_key=fact.metric_key,
                period=fact.period,
                prefer_document_id=parsed_document.doc_id,
            )
            warnings.extend(resolution.warnings)
            if resolution.winner is None:
                continue
            if resolution.winner.document_id != parsed_document.doc_id:
                continue
            facts_to_persist.append(fact)
            for item in conflicting_rows:
                if item.row.doc_id != parsed_document.doc_id:
                    superseded_ids.append(item.row.id)

        if superseded_ids:
            session.execute(
                delete(FinancialItemORM).where(FinancialItemORM.id.in_(superseded_ids))
            )
        return facts_to_persist, warnings

    def _load_company_metric_items(
        self,
        session: Session,
        *,
        company_id: str,
        exclude_doc_id: str,
    ) -> dict[str, list[_ExistingMetricItem]]:
        documents = (
            session.execute(
                select(DocumentORM).where(
                    DocumentORM.status == "completed",
                )
            )
            .scalars()
            .all()
        )
        matching_documents = {
            document.doc_id: document
            for document in documents
            if document.doc_id != exclude_doc_id
            and build_company_id(str((document.metadata_json or {}).get("company") or "").strip())
            == company_id
        }
        if not matching_documents:
            return {}

        rows = (
            session.execute(
                select(FinancialItemORM).where(
                    FinancialItemORM.fact_type == "metric",
                    FinancialItemORM.doc_id.in_(matching_documents),
                )
            )
            .scalars()
            .all()
        )
        grouped: dict[str, list[_ExistingMetricItem]] = defaultdict(list)
        for row in rows:
            if not row.metric_key or not row.period:
                continue
            document = matching_documents[row.doc_id]
            document_year = (document.metadata_json or {}).get("year")
            grouped[metric_period_key(row.metric_key, row.period)].append(
                _ExistingMetricItem(
                    row=row,
                    document_year=document_year if isinstance(document_year, int) else None,
                )
            )
        return grouped

    def get(self, doc_id: str) -> ParsedDocument:
        with self._session_factory() as session:
            row = session.execute(
                select(ParsedDocumentORM).where(ParsedDocumentORM.doc_id == doc_id)
            ).scalar_one_or_none()
            if row is None:
                raise DocumentNotFoundError(f"Parsed document not found: {doc_id}")
            return parsed_document_from_payload(row.payload)


def _existing_metric_value(row: FinancialItemORM) -> int | float | str:
    return _restore_value(row.value_numeric, row.value_text)
