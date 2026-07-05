from __future__ import annotations

from decimal import Decimal

from app.core.db.postgres_models import DocumentORM, DocumentSegmentORM, FinancialItemORM, ParsedTableORM
from src.claude_copilot.schemas.document import (
    DocumentRecord,
    DocumentSegment,
    FinancialMetricFact,
    FinancialNoteFact,
    ParsedDocument,
    ParsedTable,
)


def document_record_to_orm(record: DocumentRecord) -> DocumentORM:
    return DocumentORM(
        doc_id=record.doc_id,
        filename=record.filename,
        status=record.status.value if hasattr(record.status, "value") else str(record.status),
        created_at=record.created_at,
        updated_at=record.updated_at,
        storage_path=record.storage_path,
        parsed_path=record.parsed_path,
        segment_count=record.segment_count,
        error_message=record.error_message,
        metadata_json=record.metadata.model_dump(mode="json"),
    )


def document_record_from_orm(row: DocumentORM) -> DocumentRecord:
    payload = {
        "doc_id": row.doc_id,
        "filename": row.filename,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "storage_path": row.storage_path,
        "parsed_path": row.parsed_path,
        "segment_count": row.segment_count,
        "error_message": row.error_message,
        "metadata": row.metadata_json,
    }
    return DocumentRecord.model_validate(payload)


def parsed_table_to_orm(doc_id: str, table: ParsedTable, table_index: int) -> ParsedTableORM:
    table_pk = table.table_id or f"{doc_id}:table:{table_index}"
    return ParsedTableORM(
        id=table_pk,
        doc_id=doc_id,
        table_index=table_index,
        table_id=table.table_id,
        table_type=table.table_type,
        title=table.title,
        page=table.page,
        raw_markdown=table.raw_markdown,
        headers=list(table.headers),
        rows=[list(row) for row in table.rows],
        period_headers=list(table.period_headers),
        unit=table.unit,
        currency=table.currency,
        note_number=table.note_number,
        note_title=table.note_title,
        note_category=table.note_category,
        semantic_rows=[dict(row) for row in table.semantic_rows],
        normalized_metrics=dict(table.normalized_metrics),
        metadata_json=dict(table.metadata),
    )


def metric_fact_to_orm(doc_id: str, fact: FinancialMetricFact, item_index: int) -> FinancialItemORM:
    value_numeric, value_text = split_fact_value(fact.value)
    return FinancialItemORM(
        id=f"{doc_id}:metric:{item_index}",
        doc_id=doc_id,
        source_table_id=fact.source_table_id,
        fact_type="metric",
        metric_key=fact.metric_key,
        fact_key=None,
        statement_type=fact.statement_type,
        period=fact.period,
        value_numeric=value_numeric,
        value_text=value_text,
        unit=fact.unit,
        currency=fact.currency,
        note_number=None,
        note_title=None,
        note_category=None,
        row_label=None,
        row_type=None,
        dimensions={},
        tags=[],
        source_section=fact.source_section,
        page_range=list(fact.page_range) if fact.page_range else None,
        provenance=dict(fact.provenance),
    )


def note_fact_to_orm(doc_id: str, fact: FinancialNoteFact, item_index: int) -> FinancialItemORM:
    numeric_value = None
    text_value = None
    if fact.period_values:
        numeric_value = None
        text_value = None
    return FinancialItemORM(
        id=f"{doc_id}:note:{item_index}",
        doc_id=doc_id,
        source_table_id=fact.source_table_id,
        fact_type="note",
        metric_key=None,
        fact_key=fact.fact_key,
        statement_type=None,
        period=None,
        value_numeric=numeric_value,
        value_text=text_value,
        unit=None,
        currency=None,
        note_number=fact.note_number,
        note_title=fact.note_title,
        note_category=fact.note_category,
        row_label=fact.row_label,
        row_type=fact.row_type,
        dimensions=dict(fact.dimensions),
        tags=list(fact.tags),
        source_section=fact.source_section,
        page_range=list(fact.page_range) if fact.page_range else None,
        provenance={
            **dict(fact.provenance),
            "period_values": dict(fact.period_values),
        },
    )


def document_segment_to_orm(segment: DocumentSegment) -> DocumentSegmentORM:
    return DocumentSegmentORM(
        segment_id=segment.segment_id,
        doc_id=segment.document_id,
        parent_section_id=segment.parent_section_id,
        position=segment.position,
        content=segment.content,
        content_summary=segment.content_summary,
        keywords=list(segment.keywords),
        metadata_json=dict(segment.metadata),
    )


def document_segment_from_orm(row: DocumentSegmentORM) -> DocumentSegment:
    payload = {
        "segment_id": row.segment_id,
        "document_id": row.doc_id,
        "parent_section_id": row.parent_section_id,
        "position": row.position,
        "content": row.content,
        "content_summary": row.content_summary,
        "keywords": row.keywords,
        "metadata": row.metadata_json,
    }
    return DocumentSegment.model_validate(payload)


def parsed_document_from_payload(payload: dict) -> ParsedDocument:
    return ParsedDocument.model_validate(payload)


def split_fact_value(value: int | float | str) -> tuple[Decimal | None, str | None]:
    if isinstance(value, bool):
        return None, str(value)
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)), None
    return None, str(value)
