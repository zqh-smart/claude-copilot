from typing import Literal

from pydantic import BaseModel, Field

from src.claude_copilot.schemas.financial_data import FinancialMetricObservation
from src.claude_copilot.schemas.knowledge_graph import GraphPath


class ResearchPreviewRequest(BaseModel):
    doc_id: str
    question: str
    top_k: int = Field(default=3, ge=1, le=10)


class ResearchHit(BaseModel):
    segment_id: str
    score: float
    content: str


class QueryAnalysis(BaseModel):
    intent: Literal["semantic", "structured", "relational", "hybrid"]
    routes: list[Literal["vector", "sql", "graph"]] = Field(default_factory=list)
    metric_keys: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    needs_growth: bool = False


class MetricCalculation(BaseModel):
    metric_key: str
    yearly_values: dict[int, float] = Field(default_factory=dict)
    yoy_growth: dict[int, float] = Field(default_factory=dict)
    cagr: float | None = None


class GroundedCitation(BaseModel):
    evidence_id: str
    claim: str


class GroundedSynthesis(BaseModel):
    answer: str
    key_findings: list[str] = Field(default_factory=list)
    citations: list[GroundedCitation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)


class CriticIssue(BaseModel):
    category: Literal[
        "unsupported_claim",
        "numeric_mismatch",
        "citation_error",
        "logic_error",
        "missing_evidence",
    ]
    severity: Literal["low", "medium", "high"]
    message: str
    evidence_ids: list[str] = Field(default_factory=list)


class CriticReview(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    issues: list[CriticIssue] = Field(default_factory=list)
    summary: str


class ResearchPreviewResponse(BaseModel):
    doc_id: str
    question: str
    answer: str
    hits: list[ResearchHit] = Field(default_factory=list)
    query_analysis: QueryAnalysis | None = None
    metrics: list[FinancialMetricObservation] = Field(default_factory=list)
    calculations: list[MetricCalculation] = Field(default_factory=list)
    graph_paths: list[GraphPath] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    synthesis: GroundedSynthesis | None = None
    critic: CriticReview | None = None
    revision_count: int = 0
    grounded: bool = False
