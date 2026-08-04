"""Select metric facts allowed on the Serving track (L2 gate)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.claude_copilot.schemas.document import FinancialMetricFact, FinancialSchema, ParsedDocument
from src.claude_copilot.schemas.financial_data import FinancialMetricObservation


def fact_key(fact: FinancialMetricFact) -> str:
    return f"{fact.metric_key}::{fact.period}::{fact.value}"


def metric_period_key(metric_key: str, period: str) -> str:
    return f"{metric_key}::{period}"


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


def has_metric_provenance(fact: FinancialMetricFact) -> bool:
    if fact.source_table_id or fact.page_range or fact.source_section:
        return True
    return bool(fact.provenance)


def observation_has_provenance(observation: FinancialMetricObservation) -> bool:
    if observation.source_table_id or observation.page_range or observation.source_section:
        return True
    return bool(observation.provenance)


def is_grounded_metric_fact(
    fact: FinancialMetricFact,
    schema: FinancialSchema | None,
) -> bool:
    if fact.provenance.get("source_grounded") is True:
        return True
    if schema is None:
        return False
    gate = schema.metadata.get("serving_gate") or {}
    allowed = set(gate.get("grounded_fact_keys") or [])
    if allowed:
        return fact_key(fact) in allowed
    return False


def observation_is_grounded(observation: FinancialMetricObservation) -> bool:
    return observation.provenance.get("source_grounded") is True


def enrich_serving_fact_provenance(
    fact: FinancialMetricFact,
    schema: FinancialSchema | None,
) -> FinancialMetricFact:
    provenance = {
        **dict(fact.provenance),
        "source_grounded": is_grounded_metric_fact(fact, schema),
    }
    return fact.model_copy(update={"provenance": provenance})


def prepare_serving_metric_facts(
    schema: FinancialSchema | None,
) -> list[FinancialMetricFact]:
    return [
        enrich_serving_fact_provenance(fact, schema)
        for fact in select_serving_metric_facts(schema)
    ]


def normalize_metric_value(value: int | float | str) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{float(value):.10g}"
    return str(value).strip()


def metric_values_conflict(
    left: int | float | str,
    right: int | float | str,
) -> bool:
    return normalize_metric_value(left) != normalize_metric_value(right)


@dataclass(frozen=True)
class MetricConflictCandidate:
    value: int | float | str
    document_id: str
    document_year: int | None
    has_provenance: bool
    is_grounded: bool
    source_type: str | None = None
    source_priority: int = 0


@dataclass(frozen=True)
class MetricConflictResolution:
    winner: MetricConflictCandidate | None
    warnings: list[str]
    suppressed_document_ids: list[str]


def candidate_from_fact(
    fact: FinancialMetricFact,
    *,
    document_id: str,
    document_year: int | None,
    schema: FinancialSchema | None = None,
) -> MetricConflictCandidate:
    return MetricConflictCandidate(
        value=fact.value,
        document_id=document_id,
        document_year=document_year,
        has_provenance=has_metric_provenance(fact),
        is_grounded=is_grounded_metric_fact(fact, schema),
        source_type=str(fact.provenance.get("source_type") or "") or None,
        source_priority=int(fact.provenance.get("source_priority") or 0),
    )


def candidate_from_observation(
    observation: FinancialMetricObservation,
) -> MetricConflictCandidate:
    return MetricConflictCandidate(
        value=observation.value,
        document_id=observation.document_id,
        document_year=observation.document_year,
        has_provenance=observation_has_provenance(observation),
        is_grounded=observation_is_grounded(observation),
        source_type=str(observation.provenance.get("source_type") or "") or None,
        source_priority=int(observation.provenance.get("source_priority") or 0),
    )


def _candidate_sort_key(
    candidate: MetricConflictCandidate,
    *,
    prefer_document_id: str | None = None,
) -> tuple[Any, ...]:
    return (
        prefer_document_id is not None and candidate.document_id == prefer_document_id,
        candidate.has_provenance and candidate.is_grounded,
        candidate.is_grounded,
        candidate.has_provenance,
        candidate.source_priority,
        candidate.document_year or 0,
        candidate.document_id,
    )


def _conflict_warning(
    metric_key: str,
    period: str,
    *,
    detail: str,
) -> str:
    return f"conflicting {metric_key} values for {period}; {detail}"


def _fact_dedup_sort_key(
    fact: FinancialMetricFact,
    *,
    schema: FinancialSchema | None = None,
) -> tuple[Any, ...]:
    title = (fact.source_table_title or "").casefold()
    cash_flow_table = "现金流量" in title or "cash flow" in title
    canonical = None
    if schema is not None and schema.metrics_index:
        canonical = schema.metrics_index.get(fact.metric_key, {}).get(fact.period)
    matches_canonical = (
        canonical is not None and not metric_values_conflict(fact.value, canonical)
    )
    return (
        matches_canonical,
        is_grounded_metric_fact(fact, schema),
        cash_flow_table,
        bool(fact.source_table_id),
        fact.source_table_id or "",
    )


def dedupe_serving_metric_facts(
    facts: list[FinancialMetricFact],
    *,
    schema: FinancialSchema | None = None,
) -> list[FinancialMetricFact]:
    """Keep one fact per metric_key+period before cross-document conflict checks."""
    grouped: dict[tuple[str, str], list[FinancialMetricFact]] = {}
    for fact in facts:
        if not fact.metric_key or not fact.period:
            continue
        key = (fact.metric_key, fact.period)
        grouped.setdefault(key, []).append(fact)
    deduped: list[FinancialMetricFact] = []
    for candidates in grouped.values():
        if len(candidates) == 1:
            deduped.append(candidates[0])
            continue
        deduped.append(
            max(candidates, key=lambda fact: _fact_dedup_sort_key(fact, schema=schema))
        )
    return deduped


def resolve_metric_conflict(
    candidates: list[MetricConflictCandidate],
    *,
    metric_key: str,
    period: str,
    prefer_document_id: str | None = None,
) -> MetricConflictResolution:
    if not candidates:
        return MetricConflictResolution(winner=None, warnings=[], suppressed_document_ids=[])

    distinct_values = {normalize_metric_value(candidate.value) for candidate in candidates}
    if len(distinct_values) <= 1:
        winner = max(
            candidates,
            key=lambda candidate: _candidate_sort_key(
                candidate,
                prefer_document_id=prefer_document_id,
            ),
        )
        return MetricConflictResolution(
            winner=winner,
            warnings=[],
            suppressed_document_ids=[],
        )

    preferred = [
        candidate
        for candidate in candidates
        if candidate.has_provenance and candidate.is_grounded
    ]
    if len(preferred) == 1:
        winner = preferred[0]
        detail = f"kept grounded fact with provenance from document {winner.document_id}"
        return MetricConflictResolution(
            winner=winner,
            warnings=[_conflict_warning(metric_key, period, detail=detail)],
            suppressed_document_ids=[
                candidate.document_id
                for candidate in candidates
                if candidate.document_id != winner.document_id
            ],
        )

    if len(preferred) > 1:
        winner = max(
            preferred,
            key=lambda candidate: _candidate_sort_key(
                candidate,
                prefer_document_id=prefer_document_id,
            ),
        )
        detail = (
            "multiple grounded facts with provenance remain; "
            f"kept document {winner.document_id}"
        )
        return MetricConflictResolution(
            winner=winner,
            warnings=[_conflict_warning(metric_key, period, detail=detail)],
            suppressed_document_ids=[
                candidate.document_id
                for candidate in candidates
                if candidate.document_id != winner.document_id
            ],
        )

    winner = max(
        candidates,
        key=lambda candidate: _candidate_sort_key(
            candidate,
            prefer_document_id=prefer_document_id,
        ),
    )
    detail = (
        "no grounded fact with provenance to resolve conflict; "
        f"kept document {winner.document_id} without silent overwrite"
    )
    return MetricConflictResolution(
        winner=winner,
        warnings=[_conflict_warning(metric_key, period, detail=detail)],
        suppressed_document_ids=[
            candidate.document_id
            for candidate in candidates
            if candidate.document_id != winner.document_id
        ],
    )


def resolve_observation_conflicts(
    observations: list[FinancialMetricObservation],
) -> tuple[list[FinancialMetricObservation], list[str]]:
    grouped: dict[tuple[str, str], list[FinancialMetricObservation]] = {}
    passthrough: list[FinancialMetricObservation] = []

    for observation in observations:
        if not observation.metric_key or not observation.period:
            passthrough.append(observation)
            continue
        grouped.setdefault((observation.metric_key, observation.period), []).append(observation)

    selected: list[FinancialMetricObservation] = list(passthrough)
    warnings: list[str] = []
    for (metric_key, period), candidates in grouped.items():
        resolution = resolve_metric_conflict(
            [candidate_from_observation(candidate) for candidate in candidates],
            metric_key=metric_key,
            period=period,
        )
        if resolution.winner is None:
            continue
        winner = next(
            candidate
            for candidate in candidates
            if candidate.document_id == resolution.winner.document_id
            and not metric_values_conflict(candidate.value, resolution.winner.value)
        )
        selected.append(winner)
        warnings.extend(resolution.warnings)
    return selected, warnings
