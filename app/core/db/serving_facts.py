"""Select metric facts allowed on the Serving track (L2 gate)."""

from __future__ import annotations

from src.claude_copilot.schemas.document import FinancialMetricFact, FinancialSchema, ParsedDocument


def fact_key(fact: FinancialMetricFact) -> str:
    return f"{fact.metric_key}::{fact.period}::{fact.value}"


def select_serving_metric_facts(
    schema: FinancialSchema | None,
) -> list[FinancialMetricFact]:
    if schema is None or not schema.metric_facts:
        return []
    gate = schema.metadata.get("serving_gate") or {}
    if gate.get("allow_metric_serving") is False:
        return []
    allowed = set(gate.get("grounded_fact_keys") or [])
    if not allowed:
        return list(schema.metric_facts)
    return [fact for fact in schema.metric_facts if fact_key(fact) in allowed]


def select_serving_metric_facts_from_document(
    document: ParsedDocument,
) -> list[FinancialMetricFact]:
    return select_serving_metric_facts(document.financial_schema)
