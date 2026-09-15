from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app.core.llm import JsonChatClientProtocol

EnterpriseNodeType = Literal[
    "company",
    "subsidiary",
    "industry",
    "business_segment",
    "event",
    "metric",
    "risk",
]
EnterpriseRelationshipType = Literal[
    "OWNS",
    "OPERATES_IN",
    "AFFECTED_BY",
    "COMPETES_WITH",
    "REPORTS_METRIC",
    "HAS_RISK",
]


class LLMEntity(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    node_type: EnterpriseNodeType
    evidence: str = Field(min_length=2)


class LLMRelationship(BaseModel):
    source_name: str = Field(min_length=2, max_length=160)
    target_name: str = Field(min_length=2, max_length=160)
    relationship_type: EnterpriseRelationshipType
    evidence: str = Field(min_length=2)


class LLMSnippetExtraction(BaseModel):
    snippet_id: str
    entities: list[LLMEntity] = Field(default_factory=list)
    relationships: list[LLMRelationship] = Field(default_factory=list)


class LLMBatchExtraction(BaseModel):
    items: list[LLMSnippetExtraction] = Field(default_factory=list)


@dataclass(frozen=True)
class ExtractionResult:
    items: list[LLMSnippetExtraction]
    unsupported_fact_count: int
    missing_snippet_ids: list[str] = field(default_factory=list)


class SchemaConstrainedKGExtractor:
    """Extract enterprise KG facts and reject claims without verbatim evidence."""

    SYSTEM_PROMPT = """You extract a financial knowledge graph from frozen snippets.
Return one JSON object with key `items`. For each input snippet return exactly its snippet_id,
target entities, and relations. Allowed node_type values: company, subsidiary, industry,
business_segment, event, metric, risk. Allowed relationship_type values: OWNS, OPERATES_IN,
AFFECTED_BY, COMPETES_WITH, REPORTS_METRIC, HAS_RISK. Do not emit the focal company as an
entity. Every evidence field must be an exact non-empty substring copied from that snippet.
Do not infer facts that are not explicit. Keep entity names exactly as written. Never return
empty arrays when an explicit entity and relation appear. Required JSON shape:
{"items":[{"snippet_id":"s01","entities":[{"name":"Aurora Labs","node_type":
"subsidiary","evidence":"Huaheng Technology owns Aurora Labs, a wholly owned subsidiary."}],
"relationships":[{"source_name":"Huaheng Technology","target_name":"Aurora Labs",
"relationship_type":"OWNS","evidence":"Huaheng Technology owns Aurora Labs, a wholly owned
subsidiary."}]}]}"""

    def __init__(self, client: JsonChatClientProtocol) -> None:
        self._client = client

    def extract_batch(
        self,
        *,
        company_name: str,
        snippets: list[dict[str, str | int]],
    ) -> ExtractionResult:
        payload = self._client.complete_json(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {"company_name": company_name, "snippets": snippets},
                ensure_ascii=False,
            ),
        )
        parsed = LLMBatchExtraction.model_validate(payload)
        source_by_id = {str(item["snippet_id"]): str(item["text"]) for item in snippets}
        accepted: list[LLMSnippetExtraction] = []
        unsupported = 0
        seen: set[str] = set()
        for item in parsed.items:
            source = source_by_id.get(item.snippet_id)
            if source is None or item.snippet_id in seen:
                unsupported += len(item.entities) + len(item.relationships)
                continue
            seen.add(item.snippet_id)
            entities = [entity for entity in item.entities if entity.evidence in source]
            relationships = [
                relationship
                for relationship in item.relationships
                if relationship.evidence in source
            ]
            unsupported += len(item.entities) - len(entities)
            unsupported += len(item.relationships) - len(relationships)
            accepted.append(
                item.model_copy(update={"entities": entities, "relationships": relationships})
            )
        missing = sorted(set(source_by_id) - seen)
        return ExtractionResult(
            items=accepted,
            unsupported_fact_count=unsupported,
            missing_snippet_ids=missing,
        )
