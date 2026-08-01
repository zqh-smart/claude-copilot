"""Portfolio comparison and BI dashboard contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PortfolioDashboardRequest(BaseModel):
    company_ids: list[str] = Field(min_length=1, max_length=20)
    metric_keys: list[str] = Field(
        default_factory=lambda: ["revenue", "net_income", "total_assets"],
        min_length=1,
        max_length=10,
    )


class CompanyMetricSnapshot(BaseModel):
    company_id: str
    company_name: str
    year: int
    value: float
    unit: str | None = None
    currency: str | None = None


class MetricRanking(BaseModel):
    metric_key: str
    items: list[CompanyMetricSnapshot] = Field(default_factory=list)


class IndustryDistribution(BaseModel):
    industry: str
    company_count: int
    company_ids: list[str] = Field(default_factory=list)


class CompanyRiskProfile(BaseModel):
    company_id: str
    company_name: str
    categories: dict[str, int] = Field(default_factory=dict)
    total: int = 0


class BusinessOverlap(BaseModel):
    company_id_a: str
    company_id_b: str
    shared_segments: list[str] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0)


class PortfolioDashboardResponse(BaseModel):
    company_ids: list[str]
    rankings: list[MetricRanking] = Field(default_factory=list)
    industry_distribution: list[IndustryDistribution] = Field(default_factory=list)
    risk_heatmap: list[CompanyRiskProfile] = Field(default_factory=list)
    business_overlap: list[BusinessOverlap] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
