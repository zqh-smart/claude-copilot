"""Compare and report API contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    doc_id_a: str
    doc_id_b: str
    question: str = ""
    period: str | int | None = None
    metric_keys: list[str] | None = None
    use_workflow: bool = True


class CompareResponse(BaseModel):
    answer_markdown: str
    matrix: list[dict[str, Any]] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    workflow: str = "comparison_workflow"


class ReportOutlineRequest(BaseModel):
    doc_id: str
    question: str = ""
    top_k: int = Field(default=5, ge=1, le=20)
    use_workflow: bool = True


class ReportOutlineResponse(BaseModel):
    answer_markdown: str
    sections: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    workflow: str = "report_workflow"


class ReportExportRequest(ReportOutlineRequest):
    title: str = "金融研究报告"
    format: Literal["html", "pdf"] = "pdf"


class ReportBundleExportRequest(BaseModel):
    doc_ids: list[str] = Field(min_length=1, max_length=20)
    question: str = ""
    top_k: int = Field(default=5, ge=1, le=20)
    report_type: Literal["investment", "risk"] = "investment"
    title: str = "金融研究报告"
    format: Literal["html", "pdf"] = "pdf"
