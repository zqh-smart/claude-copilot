from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db.postgres_models import DocumentORM, FinancialItemORM, ParsedTableORM
from app.core.db.protocols import DocumentRepositoryProtocol, ParsedDocumentRepositoryProtocol
from app.core.db.serving_facts import select_serving_metric_facts
from app.core.errors import DocumentNotFoundError
from src.claude_copilot.entity_resolution import build_canonical_company_id
from src.claude_copilot.schemas.document import DocumentProcessingStatus
from src.claude_copilot.schemas.financial_data import CompanySummary, FinancialMetricObservation


def build_company_id(company_name: str) -> str:
    return build_canonical_company_id(company_name)


def extract_period_year(period: str | None) -> int | None:
    if not period:
        return None
    match = re.search(r"\b(19\d{2}|20\d{2})\b", period)
    return int(match.group(1)) if match else None


class LocalFinancialDataRepository:
    def __init__(
        self,
        document_repository: DocumentRepositoryProtocol,
        parsed_document_repository: ParsedDocumentRepositoryProtocol,
    ) -> None:
        self._document_repository = document_repository
        self._parsed_document_repository = parsed_document_repository

    def list_companies(self) -> list[CompanySummary]:
        grouped: dict[str, dict] = {}
        for record in self._completed_company_documents():
            company = record.metadata.company or ""
            company_id = build_company_id(company)
            entry = grouped.setdefault(
                company_id,
                {"name": company, "years": set(), "document_count": 0, "metric_count": 0},
            )
            entry["document_count"] += 1
            if record.metadata.year is not None:
                entry["years"].add(record.metadata.year)
            try:
                parsed = self._parsed_document_repository.get(record.doc_id)
            except DocumentNotFoundError:
                continue
            facts = select_serving_metric_facts(parsed.financial_schema)
            entry["metric_count"] += len(facts)
            entry["years"].update(
                year for fact in facts if (year := extract_period_year(fact.period)) is not None
            )

        return sorted(
            [
                CompanySummary(
                    company_id=company_id,
                    name=item["name"],
                    years=sorted(item["years"]),
                    document_count=item["document_count"],
                    metric_count=item["metric_count"],
                )
                for company_id, item in grouped.items()
            ],
            key=lambda item: item.name.casefold(),
        )

    def get_company(self, company_id: str) -> CompanySummary | None:
        return next(
            (company for company in self.list_companies() if company.company_id == company_id),
            None,
        )

    def query_metrics(
        self,
        company_id: str,
        *,
        year: int | None = None,
        metric_key: str | None = None,
        statement_type: str | None = None,
        limit: int = 500,
    ) -> list[FinancialMetricObservation]:
        observations: list[FinancialMetricObservation] = []
        for record in self._completed_company_documents():
            company = record.metadata.company or ""
            if build_company_id(company) != company_id:
                continue
            try:
                parsed = self._parsed_document_repository.get(record.doc_id)
            except DocumentNotFoundError:
                continue
            facts = select_serving_metric_facts(parsed.financial_schema)
            for fact in facts:
                period_year = extract_period_year(fact.period)
                if year is not None and period_year != year:
                    continue
                if metric_key is not None and fact.metric_key != metric_key:
                    continue
                if statement_type is not None and fact.statement_type != statement_type:
                    continue
                observations.append(
                    FinancialMetricObservation(
                        company_id=company_id,
                        company=company,
                        document_id=record.doc_id,
                        document_year=record.metadata.year,
                        metric_key=fact.metric_key,
                        period=fact.period,
                        period_year=period_year,
                        value=fact.value,
                        statement_type=fact.statement_type,
                        unit=fact.unit,
                        currency=fact.currency,
                        source_table_id=fact.source_table_id,
                        source_table_title=fact.source_table_title,
                        source_section=fact.source_section,
                        page_range=fact.page_range,
                        provenance=dict(fact.provenance),
                    )
                )
        return _sort_observations(observations)[:limit]

    def _completed_company_documents(self):
        return [
            record
            for record in self._document_repository.list()
            if record.status == DocumentProcessingStatus.COMPLETED and record.metadata.company
        ]


class PostgresFinancialDataRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_companies(self) -> list[CompanySummary]:
        with self._session_factory() as session:
            documents = (
                session.execute(
                    select(DocumentORM).where(
                        DocumentORM.status == DocumentProcessingStatus.COMPLETED.value
                    )
                )
                .scalars()
                .all()
            )
            counts: dict[str, int] = defaultdict(int)
            periods: dict[str, set[int]] = defaultdict(set)
            metric_rows = session.execute(
                select(
                    FinancialItemORM.doc_id,
                    FinancialItemORM.period,
                ).where(FinancialItemORM.fact_type == "metric")
            ).all()
            for doc_id, period in metric_rows:
                counts[doc_id] += 1
                if (period_year := extract_period_year(period)) is not None:
                    periods[doc_id].add(period_year)

            grouped: dict[str, dict] = {}
            for document in documents:
                company = str((document.metadata_json or {}).get("company") or "").strip()
                if not company:
                    continue
                company_id = build_company_id(company)
                entry = grouped.setdefault(
                    company_id,
                    {"name": company, "years": set(), "document_count": 0, "metric_count": 0},
                )
                entry["document_count"] += 1
                document_year = (document.metadata_json or {}).get("year")
                if isinstance(document_year, int):
                    entry["years"].add(document_year)
                entry["years"].update(periods[document.doc_id])
                entry["metric_count"] += counts[document.doc_id]

            return sorted(
                [
                    CompanySummary(
                        company_id=company_id,
                        name=item["name"],
                        years=sorted(item["years"]),
                        document_count=item["document_count"],
                        metric_count=item["metric_count"],
                    )
                    for company_id, item in grouped.items()
                ],
                key=lambda item: item.name.casefold(),
            )

    def get_company(self, company_id: str) -> CompanySummary | None:
        return next(
            (company for company in self.list_companies() if company.company_id == company_id),
            None,
        )

    def query_metrics(
        self,
        company_id: str,
        *,
        year: int | None = None,
        metric_key: str | None = None,
        statement_type: str | None = None,
        limit: int = 500,
    ) -> list[FinancialMetricObservation]:
        with self._session_factory() as session:
            documents = (
                session.execute(
                    select(DocumentORM).where(
                        DocumentORM.status == DocumentProcessingStatus.COMPLETED.value
                    )
                )
                .scalars()
                .all()
            )
            matching_documents = {
                document.doc_id: document
                for document in documents
                if (company := str((document.metadata_json or {}).get("company") or "").strip())
                and build_company_id(company) == company_id
            }
            if not matching_documents:
                return []

            statement = select(FinancialItemORM).where(
                FinancialItemORM.fact_type == "metric",
                FinancialItemORM.doc_id.in_(matching_documents),
            )
            if metric_key is not None:
                statement = statement.where(FinancialItemORM.metric_key == metric_key)
            if statement_type is not None:
                statement = statement.where(FinancialItemORM.statement_type == statement_type)
            rows = session.execute(statement).scalars().all()

            table_rows = (
                session.execute(
                    select(ParsedTableORM).where(ParsedTableORM.doc_id.in_(matching_documents))
                )
                .scalars()
                .all()
            )
            titles = {
                (table.doc_id, table.table_id): table.title
                for table in table_rows
                if table.table_id
            }

            observations: list[FinancialMetricObservation] = []
            for row in rows:
                period_year = extract_period_year(row.period)
                if year is not None and period_year != year:
                    continue
                document = matching_documents[row.doc_id]
                company = str(document.metadata_json.get("company"))
                value = _restore_value(row.value_numeric, row.value_text)
                observations.append(
                    FinancialMetricObservation(
                        company_id=company_id,
                        company=company,
                        document_id=row.doc_id,
                        document_year=document.metadata_json.get("year"),
                        metric_key=row.metric_key or "",
                        period=row.period or "",
                        period_year=period_year,
                        value=value,
                        statement_type=row.statement_type,
                        unit=row.unit,
                        currency=row.currency,
                        source_table_id=row.source_table_id,
                        source_table_title=titles.get((row.doc_id, row.source_table_id)),
                        source_section=row.source_section,
                        page_range=tuple(row.page_range) if row.page_range else None,
                        provenance=dict(row.provenance or {}),
                    )
                )
            return _sort_observations(observations)[:limit]


def _restore_value(value_numeric: Decimal | None, value_text: str | None) -> int | float | str:
    if value_numeric is None:
        return value_text or ""
    if value_numeric == value_numeric.to_integral_value():
        return int(value_numeric)
    return float(value_numeric)


def _sort_observations(
    observations: list[FinancialMetricObservation],
) -> list[FinancialMetricObservation]:
    return sorted(
        observations,
        key=lambda item: (
            item.period_year is None,
            item.period_year or 0,
            item.metric_key,
            item.document_year or 0,
            item.document_id,
        ),
    )
