from app.workflows.comparator.graph import (
    build_comparator_graph,
    build_comparison_matrix,
    normalize_metric_facts,
)
from src.claude_copilot.schemas.document import FinancialMetricFact


def test_normalize_metric_facts_prefers_larger_absolute_value() -> None:
    facts = [
        FinancialMetricFact(metric_key="revenue", period="2023", value=4.35),
        FinancialMetricFact(metric_key="revenue", period="2023", value=469_378_042.95),
    ]

    normalized = normalize_metric_facts(facts)

    assert len(normalized) == 1
    assert normalized[0]["value"] == 469_378_042.95
    assert normalized[0]["period_year"] == 2023


def test_build_comparison_matrix_delta_and_delta_pct() -> None:
    metrics_a = [
        {"metric_key": "revenue", "period": "2023", "period_year": 2023, "value": 100.0},
        {"metric_key": "net_income", "period": "2023", "period_year": 2023, "value": 10.0},
    ]
    metrics_b = [
        {"metric_key": "revenue", "period": "2023", "period_year": 2023, "value": 125.0},
        {"metric_key": "net_income", "period": "2023", "period_year": 2023, "value": 12.0},
    ]

    matrix = build_comparison_matrix(metrics_a, metrics_b)

    assert len(matrix) == 2
    revenue = next(row for row in matrix if row["metric_key"] == "revenue")
    assert revenue["value_a"] == 100.0
    assert revenue["value_b"] == 125.0
    assert revenue["delta"] == 25.0
    assert revenue["delta_pct"] == 0.25


def test_build_comparison_matrix_filters_by_metric_keys_and_period() -> None:
    metrics_a = [
        {"metric_key": "revenue", "period": "2022", "period_year": 2022, "value": 90.0},
        {"metric_key": "revenue", "period": "2023", "period_year": 2023, "value": 100.0},
        {"metric_key": "net_income", "period": "2023", "period_year": 2023, "value": 10.0},
    ]
    metrics_b = [
        {"metric_key": "revenue", "period": "2022", "period_year": 2022, "value": 95.0},
        {"metric_key": "revenue", "period": "2023", "period_year": 2023, "value": 120.0},
        {"metric_key": "net_income", "period": "2023", "period_year": 2023, "value": 11.0},
    ]

    matrix = build_comparison_matrix(
        metrics_a,
        metrics_b,
        metric_keys=["revenue"],
        period=2023,
    )

    assert len(matrix) == 1
    assert matrix[0]["metric_key"] == "revenue"
    assert matrix[0]["period"] == "2023"
    assert matrix[0]["delta"] == 20.0


def test_comparator_graph_invoke_with_mocked_loaders() -> None:
    def load_metrics(_state: dict) -> dict:
        return {
            "company_a": "Alpha Corp",
            "company_b": "Beta Corp",
            "metrics_a": [
                {"metric_key": "revenue", "period": "2023", "period_year": 2023, "value": 100.0},
            ],
            "metrics_b": [
                {"metric_key": "revenue", "period": "2023", "period_year": 2023, "value": 150.0},
            ],
            "warnings": [],
        }

    compiled = build_comparator_graph(load_fn=load_metrics)
    result = compiled.invoke(
        {
            "doc_id_a": "doc-a",
            "doc_id_b": "doc-b",
            "question": "对比两家营收",
        }
    )

    assert result["matrix"][0]["delta"] == 50.0
    assert "Alpha Corp" in result["answer"]
    assert "Beta Corp" in result["answer"]
    assert "差异=50" in result["answer"] or "差异=50.0" in result["answer"]


def test_comparator_graph_missing_side_metrics_still_produces_answer() -> None:
    def load_metrics(_state: dict) -> dict:
        return {
            "company_a": "Alpha Corp",
            "company_b": "Beta Corp",
            "metrics_a": [
                {"metric_key": "revenue", "period": "2023", "period_year": 2023, "value": 100.0},
                {"metric_key": "net_income", "period": "2023", "period_year": 2023, "value": 10.0},
            ],
            "metrics_b": [
                {"metric_key": "revenue", "period": "2023", "period_year": 2023, "value": 120.0},
            ],
            "warnings": [],
        }

    compiled = build_comparator_graph(load_fn=load_metrics)
    result = compiled.invoke(
        {
            "doc_id_a": "doc-a",
            "doc_id_b": "doc-b",
        }
    )

    assert any("缺少" in warning for warning in result["warnings"])
    assert "Alpha Corp" in result["answer"]
    assert "Beta Corp" in result["answer"]
    assert result["answer"]
