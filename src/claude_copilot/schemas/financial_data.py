from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CompanySummary(BaseModel):
    company_id: str
    name: str
    years: list[int] = Field(default_factory=list)
    document_count: int = 0
    metric_count: int = 0


class FinancialMetricObservation(BaseModel):
    company_id: str
    company: str
    document_id: str
    document_year: int | None = None
    metric_key: str
    period: str
    period_year: int | None = None
    value: int | float | str
    statement_type: str | None = None
    unit: str | None = None
    currency: str | None = None
    source_table_id: str | None = None
    source_table_title: str | None = None
    source_section: str | None = None
    page_range: tuple[int, int] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class FinancialMetricsResponse(BaseModel):
    company: CompanySummary
    filters: dict[str, Any] = Field(default_factory=dict)
    count: int
    items: list[FinancialMetricObservation] = Field(default_factory=list)


class MetricGrowthPoint(BaseModel):
    year: int
    period: str
    value: float
    yoy_growth: float | None = None
    document_id: str


class MetricTrendResponse(BaseModel):
    company: CompanySummary
    metric_key: str
    unit: str | None = None
    currency: str | None = None
    points: list[MetricGrowthPoint] = Field(default_factory=list)
    cagr: float | None = None
    warnings: list[str] = Field(default_factory=list)
    observations: list[FinancialMetricObservation] = Field(default_factory=list)


class FusedMetricFact(BaseModel):
    metric_key: str
    period: str
    value: int | float | str
    statement_type: str | None = None
    unit: str | None = None
    currency: str | None = None
    winner_document_id: str
    source_document_ids: list[str] = Field(default_factory=list)
    suppressed_document_ids: list[str] = Field(default_factory=list)
    source_table_id: str | None = None
    source_section: str | None = None
    page_range: tuple[int, int] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class MetricFusionConflict(BaseModel):
    metric_key: str
    period: str
    winner_document_id: str
    suppressed_document_ids: list[str] = Field(default_factory=list)
    candidate_values: dict[str, int | float | str] = Field(default_factory=dict)
    resolution: str


class FinancialKnowledgeFusionResponse(BaseModel):
    company: CompanySummary
    document_ids: list[str] = Field(default_factory=list)
    reporting_periods: list[str] = Field(default_factory=list)
    facts: list[FusedMetricFact] = Field(default_factory=list)
    metrics_index: dict[str, dict[str, int | float | str]] = Field(default_factory=dict)
    conflicts: list[MetricFusionConflict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
