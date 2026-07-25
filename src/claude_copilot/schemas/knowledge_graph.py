from typing import Any, Literal

from pydantic import BaseModel, Field

GraphNodeType = Literal[
    "company",
    "subsidiary",
    "industry",
    "business_segment",
    "event",
    "document",
    "metric",
    "risk",
]
GraphRelationshipType = Literal[
    "HAS_DOCUMENT",
    "REPORTS_METRIC",
    "HAS_RISK",
    "OWNS",
    "OPERATES_IN",
    "AFFECTED_BY",
    "COMPETES_WITH",
    "EVIDENCED_BY",
]


class KnowledgeGraphNode(BaseModel):
    node_id: str
    node_type: GraphNodeType
    name: str
    document_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphRelationship(BaseModel):
    relationship_id: str
    relationship_type: GraphRelationshipType
    source_node_id: str
    target_node_id: str
    document_id: str
    page_range: tuple[int, int] | None = None
    evidence_text: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    properties: dict[str, Any] = Field(default_factory=dict)


class DocumentKnowledgeGraph(BaseModel):
    document_id: str
    company_id: str | None = None
    nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    relationships: list[KnowledgeGraphRelationship] = Field(default_factory=list)


class CompanyKnowledgeGraph(BaseModel):
    company_id: str
    company_name: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    relationships: list[KnowledgeGraphRelationship] = Field(default_factory=list)


class GraphPath(BaseModel):
    path_id: str
    summary: str
    score: float = Field(ge=0.0, le=1.0)
    nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    relationships: list[KnowledgeGraphRelationship] = Field(default_factory=list)
