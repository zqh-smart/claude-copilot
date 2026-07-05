from __future__ import annotations

from datetime import datetime

from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DocumentORM(Base):
    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")

    __table_args__ = (
        Index("ix_documents_status", "status"),
        Index("ix_documents_created_at", "created_at"),
        Index("ix_documents_metadata_gin", "metadata", postgresql_using="gin"),
    )


class ParsedDocumentORM(Base):
    __tablename__ = "parsed_documents"

    doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_parsed_documents_payload_gin", "payload", postgresql_using="gin"),
    )


class ParsedTableORM(Base):
    __tablename__ = "parsed_tables"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    table_index: Mapped[int] = mapped_column(Integer, nullable=False)
    table_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    table_type: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    headers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    rows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    period_headers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_category: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    semantic_rows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    normalized_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")

    __table_args__ = (
        Index("ux_parsed_tables_doc_id_table_index", "doc_id", "table_index", unique=True),
        Index("ix_parsed_tables_headers_gin", "headers", postgresql_using="gin"),
        Index("ix_parsed_tables_rows_gin", "rows", postgresql_using="gin"),
        Index("ix_parsed_tables_period_headers_gin", "period_headers", postgresql_using="gin"),
        Index("ix_parsed_tables_semantic_rows_gin", "semantic_rows", postgresql_using="gin"),
        Index("ix_parsed_tables_normalized_metrics_gin", "normalized_metrics", postgresql_using="gin"),
        Index("ix_parsed_tables_metadata_gin", "metadata", postgresql_using="gin"),
    )


class FinancialItemORM(Base):
    __tablename__ = "financial_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_table_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    fact_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    metric_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    fact_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    statement_type: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    period: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    value_numeric: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_category: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    row_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimensions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    source_section: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_range: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    __table_args__ = (
        Index(
            "ix_financial_items_doc_metric_period",
            "doc_id",
            "metric_key",
            "period",
        ),
        Index("ix_financial_items_dimensions_gin", "dimensions", postgresql_using="gin"),
        Index("ix_financial_items_tags_gin", "tags", postgresql_using="gin"),
        Index("ix_financial_items_page_range_gin", "page_range", postgresql_using="gin"),
        Index("ix_financial_items_provenance_gin", "provenance", postgresql_using="gin"),
    )


class DocumentSegmentORM(Base):
    __tablename__ = "document_segments"

    segment_id: Mapped[str] = mapped_column(Text, primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_section_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(content, ''))", persisted=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ux_document_segments_doc_id_position", "doc_id", "position", unique=True),
        Index("ix_document_segments_keywords_gin", "keywords", postgresql_using="gin"),
        Index("ix_document_segments_metadata_gin", "metadata", postgresql_using="gin"),
        Index("ix_document_segments_search_vector_gin", "search_vector", postgresql_using="gin"),
    )
