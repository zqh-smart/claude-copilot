from app.core.db.serving_facts import select_serving_metric_facts
from src.claude_copilot.schemas.document import FinancialMetricFact, FinancialSchema


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
