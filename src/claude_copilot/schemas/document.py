from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentProcessingStatus(StrEnum):
    WAITING = "waiting"
    PARSING = "parsing"
    CLEANING = "cleaning"
    CHUNKING = "chunking"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ParsedSection(BaseModel):
    section_id: str | None = None
    title: str | None = None
    content: str
    section_type: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedPageBlock(BaseModel):
    block_id: str | None = None
    block_type: str = "paragraph"
    text: str = ""
    page: int | None = None
    order: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedTable(BaseModel):
    table_id: str | None = None
    table_type: str | None = None
    title: str | None = None
    raw_markdown: str | None = None
    page: int | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    footnotes: list[str] = Field(default_factory=list)
    period_headers: list[str] = Field(default_factory=list)
    unit: str | None = None
    currency: str | None = None
    normalized_metrics: dict[str, Any] = Field(default_factory=dict)
    note_number: str | None = None
    note_title: str | None = None
    note_category: str | None = None
    semantic_rows: list[dict[str, Any]] = Field(default_factory=list)
    source_section: str | None = None
    source_block_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParseIssue(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    page: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ParseQualityReport(BaseModel):
    route: str | None = None
    confidence: float | None = None
    text_coverage: float | None = None
    empty_page_count: int = 0
    table_count: int = 0
    issue_count: int = 0


class DocumentMetadata(BaseModel):
    doc_type: str
    source: str
    filename: str | None = None
    extension: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    parse_backend: str | None = None
    parse_route: str | None = None
    parse_strategy: str | None = None
    page_count: int | None = None
    parsed_page_range: tuple[int, int] | None = None
    parsed_page_count: int | None = None
    content_quality_score: float | None = None
    company: str | None = None
    year: int | None = None


class DocumentSegment(BaseModel):
    segment_id: str
    document_id: str
    parent_section_id: str | None = None
    position: int
    content: str
    content_summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinancialMetricFact(BaseModel):
    metric_key: str
    period: str
    value: int | float | str
    statement_type: str | None = None
    unit: str | None = None
    currency: str | None = None
    source_table_id: str | None = None
    source_table_title: str | None = None
    source_section: str | None = None
    page_range: tuple[int, int] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class FinancialStatementSchema(BaseModel):
    table_id: str | None = None
    statement_type: str | None = None
    title: str | None = None
    period_headers: list[str] = Field(default_factory=list)
    unit: str | None = None
    currency: str | None = None
    source_section: str | None = None
    page_range: tuple[int, int] | None = None
    metrics: dict[str, dict[str, int | float | str]] = Field(default_factory=dict)
    footnotes: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class FinancialNoteFact(BaseModel):
    fact_key: str
    note_number: str | None = None
    note_title: str | None = None
    note_category: str | None = None
    row_label: str | None = None
    row_type: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)
    period_values: dict[str, int | float | str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    source_table_id: str | None = None
    source_section: str | None = None
    page_range: tuple[int, int] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class FinancialNoteSchema(BaseModel):
    table_id: str | None = None
    note_number: str | None = None
    note_title: str | None = None
    note_category: str | None = None
    period_headers: list[str] = Field(default_factory=list)
    dimension_headers: list[str] = Field(default_factory=list)
    semantic_rows: list[dict[str, Any]] = Field(default_factory=list)
    note_facts: list[FinancialNoteFact] = Field(default_factory=list)
    footnotes: list[str] = Field(default_factory=list)
    source_section: str | None = None
    page_range: tuple[int, int] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class SemanticSectionSchema(BaseModel):
    section_id: str | None = None
    section_type: str | None = None
    title: str | None = None
    page_range: tuple[int, int] | None = None
    confidence: float | None = None
    evidence_text: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class FinancialSchema(BaseModel):
    company: str | None = None
    year: int | None = None
    reporting_periods: list[str] = Field(default_factory=list)
    statements: list[FinancialStatementSchema] = Field(default_factory=list)
    notes: list[FinancialNoteSchema] = Field(default_factory=list)
    semantic_sections: list[SemanticSectionSchema] = Field(default_factory=list)
    metric_facts: list[FinancialMetricFact] = Field(default_factory=list)
    note_facts: list[FinancialNoteFact] = Field(default_factory=list)
    metrics_index: dict[str, dict[str, int | float | str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    doc_id: str
    metadata: DocumentMetadata
    raw_text: str = ""
    sections: list[ParsedSection] = Field(default_factory=list)
    page_blocks: list[ParsedPageBlock] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    financial_schema: FinancialSchema | None = None
    issues: list[ParseIssue] = Field(default_factory=list)
    quality: ParseQualityReport | None = None
    segments: list[DocumentSegment] = Field(default_factory=list)


class DocumentRecord(BaseModel):
    doc_id: str
    filename: str
    status: DocumentProcessingStatus
    created_at: datetime
    updated_at: datetime
    storage_path: str
    parsed_path: str | None = None
    segment_count: int = 0
    error_message: str | None = None
    metadata: DocumentMetadata
