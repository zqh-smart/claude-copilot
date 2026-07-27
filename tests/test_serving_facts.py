from app.core.db.serving_facts import (
    MetricConflictCandidate,
    candidate_from_fact,
    enrich_serving_fact_provenance,
    prepare_serving_metric_facts,
    resolve_metric_conflict,
    select_serving_metric_facts,
)
from src.claude_copilot.schemas.document import FinancialMetricFact, FinancialSchema


def _fact(
    *,
    metric_key: str = "revenue",
    period: str = "2021",
    value: int | float = 100,
    source_table_id: str | None = None,
    provenance: dict | None = None,
) -> FinancialMetricFact:
    return FinancialMetricFact(
        metric_key=metric_key,
        period=period,
        value=value,
        source_table_id=source_table_id,
        provenance=provenance or {},
    )


def _schema(*facts: FinancialMetricFact, grounded_keys: list[str] | None = None) -> FinancialSchema:
    metadata = {"serving_gate": {"allow_metric_serving": True, "grounded_fact_keys": grounded_keys or []}}
    return FinancialSchema(metric_facts=list(facts), metadata=metadata)


def test_select_serving_metric_facts_respects_gate_allowlist() -> None:
    schema = FinancialSchema(
        metric_facts=[
            FinancialMetricFact(metric_key="revenue", period="2021", value=100),
            FinancialMetricFact(metric_key="revenue", period="2020", value=90),
        ],
        metadata={
            "serving_gate": {
                "allow_metric_serving": True,
                "grounded_fact_keys": ["revenue::2021::100"],
            }
        },
    )
    facts = select_serving_metric_facts(schema)
    assert len(facts) == 1
    assert facts[0].period == "2021"


def test_select_serving_metric_facts_blocks_when_gate_denies() -> None:
    schema = FinancialSchema(
        metric_facts=[FinancialMetricFact(metric_key="revenue", period="2021", value=100)],
        metadata={"serving_gate": {"allow_metric_serving": False, "grounded_fact_keys": []}},
    )
    assert select_serving_metric_facts(schema) == []


def test_prepare_serving_metric_facts_marks_grounded_provenance() -> None:
    schema = _schema(
        _fact(value=100, source_table_id="income-table"),
        grounded_keys=["revenue::2021::100"],
    )
    facts = prepare_serving_metric_facts(schema)
    assert facts[0].provenance["source_grounded"] is True


def test_resolve_metric_conflict_prefers_grounded_fact_with_provenance() -> None:
    grounded = candidate_from_fact(
        _fact(value=100, source_table_id="table-a"),
        document_id="doc-grounded",
        document_year=2021,
        schema=_schema(_fact(value=100, source_table_id="table-a"), grounded_keys=["revenue::2021::100"]),
    )
    ungrounded = MetricConflictCandidate(
        value=200,
        document_id="doc-ungrounded",
        document_year=2024,
        has_provenance=True,
        is_grounded=False,
    )

    resolution = resolve_metric_conflict(
        [ungrounded, grounded],
        metric_key="revenue",
        period="2021",
    )

    assert resolution.winner == grounded
    assert resolution.warnings
    assert "kept grounded fact with provenance" in resolution.warnings[0]
    assert resolution.suppressed_document_ids == ["doc-ungrounded"]


def test_resolve_metric_conflict_warns_when_no_grounded_winner() -> None:
    weaker = MetricConflictCandidate(
        value=100,
        document_id="doc-a",
        document_year=2021,
        has_provenance=False,
        is_grounded=False,
    )
    newer = MetricConflictCandidate(
        value=200,
        document_id="doc-b",
        document_year=2024,
        has_provenance=False,
        is_grounded=False,
    )

    resolution = resolve_metric_conflict(
        [weaker, newer],
        metric_key="revenue",
        period="2021",
    )

    assert resolution.winner == newer
    assert "no grounded fact with provenance" in resolution.warnings[0]
    assert "without silent overwrite" in resolution.warnings[0]


def test_resolve_metric_conflict_keeps_loser_from_becoming_sole_survivor() -> None:
    grounded = candidate_from_fact(
        _fact(value=100, source_table_id="table-a"),
        document_id="doc-grounded",
        document_year=2021,
        schema=_schema(_fact(value=100, source_table_id="table-a"), grounded_keys=["revenue::2021::100"]),
    )
    ungrounded = MetricConflictCandidate(
        value=200,
        document_id="doc-ungrounded",
        document_year=2024,
        has_provenance=True,
        is_grounded=False,
    )

    resolution = resolve_metric_conflict(
        [ungrounded, grounded],
        metric_key="revenue",
        period="2021",
    )

    assert resolution.winner.document_id == "doc-grounded"
    assert resolution.winner.value == 100
    assert "doc-ungrounded" in resolution.suppressed_document_ids


def test_enrich_serving_fact_provenance_reads_existing_grounded_flag() -> None:
    fact = _fact(provenance={"source_grounded": True})
    enriched = enrich_serving_fact_provenance(fact, None)
    assert enriched.provenance["source_grounded"] is True
