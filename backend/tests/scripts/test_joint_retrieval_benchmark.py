from scripts.run_joint_retrieval_benchmark import _compare_to_baseline


def _report(*, total: int, recall: float = 0.9) -> dict:
    return {
        "aggregate": {
            "total": total,
            "passed": total,
            "pass_rate": 1.0,
            "gate_total": 18,
            "gate_passed": 18,
            "benchmark_total": total - 18,
            "benchmark_passed": total - 18,
        },
        "diagnostics": {
            "ranking": {
                "recall_at_5": recall,
                "mrr_at_10": 0.9,
                "ndcg_at_10": 0.9,
                "hard_negative_rate_at_5": 0.3,
                "explicit_relevance_cases": 33,
            },
            "abstention": {"evaluated_cases": 48, "accuracy": 1.0},
        },
    }


def test_compare_rejects_metrics_from_a_different_corpus() -> None:
    baseline = _report(total=156)
    current = _report(total=95, recall=0.99)

    result = _compare_to_baseline(current=current, baseline=baseline)

    assert result["net_verdict"] == "negative"
    assert "corpus drift: aggregate.total 156 -> 95" in result["regressions"]
    assert "corpus drift: aggregate.benchmark_total 138 -> 77" in result["regressions"]


def test_compare_accepts_non_regressing_metrics_on_same_corpus() -> None:
    baseline = _report(total=156)
    current = _report(total=156, recall=0.92)

    result = _compare_to_baseline(current=current, baseline=baseline)

    assert result["net_verdict"] == "non_negative"
    assert result["regressions"] == []
