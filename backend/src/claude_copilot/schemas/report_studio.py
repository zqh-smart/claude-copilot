"""Report studio contracts: templates, drafts, citations, assist."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReportTemplateId = Literal[
    "comprehensive_financial",
    "annual_operations",
    "profitability",
    "cash_and_solvency",
    "financial_risk",
    "period_comparison",
]
ReportLanguage = Literal["zh", "en"]
ReportLength = Literal["standard", "brief", "long"]
DraftStatus = Literal["draft", "revised", "final"]


class ReportTemplateChapter(BaseModel):
    chapter_id: str
    title: str
    hints: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(default_factory=list)
    section_hints: list[str] = Field(default_factory=list)
    analysis_requirements: list[str] = Field(default_factory=list)
    must_cite: bool = True


class ReportTemplate(BaseModel):
    template_id: ReportTemplateId
    name: str
    category: str
    description: str
    scenario: str = ""
    chapters: list[ReportTemplateChapter]


class ReportCitation(BaseModel):
    citation_id: str
    doc_id: str
    filename: str
    section_title: str | None = None
    page: int | None = None
    excerpt: str = ""
    path_label: str
    metric_key: str | None = None


class ReportDraftSection(BaseModel):
    section_id: str
    chapter_id: str
    title: str
    content: str
    editor_json: dict[str, Any] | None = None
    citation_ids: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(default_factory=list)
    analysis_requirements: list[str] = Field(default_factory=list)


class ReportDraftSource(BaseModel):
    doc_id: str
    filename: str
    company: str | None = None
    year: int | None = None
    doc_type: str | None = None


class ReportDraft(BaseModel):
    draft_id: str
    title: str
    template_id: ReportTemplateId
    language: ReportLanguage = "zh"
    length: ReportLength = "standard"
    prompt: str = ""
    status: DraftStatus = "draft"
    sources: list[ReportDraftSource] = Field(default_factory=list)
    sections: list[ReportDraftSection] = Field(default_factory=list)
    citations: list[ReportCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CreateReportDraftRequest(BaseModel):
    doc_ids: list[str] = Field(min_length=1, max_length=20)
    template_id: ReportTemplateId
    prompt: str = ""
    language: ReportLanguage = "zh"
    length: ReportLength = "standard"
    title: str | None = None
    top_k: int = Field(default=6, ge=1, le=20)


class PatchReportDraftRequest(BaseModel):
    title: str | None = None
    status: DraftStatus | None = None
    sections: list[ReportDraftSection] | None = None


class AssistReportDraftRequest(BaseModel):
    section_id: str
    instruction: str = "润色并保持引用"
    apply: bool = False


class AssistReportDraftResponse(BaseModel):
    section_id: str
    suggested_content: str
    applied: bool
    draft: ReportDraft | None = None


class ReportDraftSummary(BaseModel):
    draft_id: str
    title: str
    template_id: ReportTemplateId
    status: DraftStatus
    source_count: int
    updated_at: datetime


class ExportReportDraftRequest(BaseModel):
    format: Literal["html", "pdf"] = "html"
    title: str | None = None


class ReportStudioCatalog(BaseModel):
    templates: list[ReportTemplate]
    extra: dict[str, Any] = Field(default_factory=dict)
