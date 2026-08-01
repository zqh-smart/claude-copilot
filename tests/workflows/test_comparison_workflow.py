from app.workflows.comparison_workflow.graph import (
    build_comparison_workflow_graph,
    compose_comparison_workflow_answer,
)


def test_compose_comparison_workflow_answer_sections() -> None:
    text = compose_comparison_workflow_answer(
        compare_answer="revenue 差额明显",
        risk_summary_a="2 条 · market_risk",
        risk_summary_b="未命中 HAS_RISK",
        warnings=["缺一期指标"],
    )
    assert "§5.4" in text
    assert "财务指标对比" in text
    assert "风险对照" in text
    assert "market_risk" in text
    assert "缺一期指标" in text


def test_comparison_workflow_graph_with_injected_steps() -> None:
    def prepare(state: dict) -> dict:
        return {"warnings": list(state.get("warnings") or [])}

    def compare(_state: dict) -> dict:
        return {
            "compare_answer": "矩阵：A revenue > B",
            "compare_matrix": [{"metric_key": "revenue"}],
            "compare_highlights": ["revenue"],
        }

    def risk(_state: dict) -> dict:
        return {
            "risk_summary_a": "1 条 · liquidity_risk",
            "risk_summary_b": "1 条 · market_risk",
        }

    graph = build_comparison_workflow_graph(
        prepare_fn=prepare,
        compare_fn=compare,
        risk_fn=risk,
    )
    result = graph.invoke(
        {"doc_id_a": "a", "doc_id_b": "b", "question": "对比两家公司"}
    )
    assert "§5.4" in result["answer"]
    assert "A revenue > B" in result["answer"]
    assert "liquidity_risk" in result["answer"]
    assert result["compare_matrix"][0]["metric_key"] == "revenue"


def test_comparison_workflow_missing_doc_id_b_warns_empty_matrix() -> None:
    result = build_comparison_workflow_graph().invoke(
        {"doc_id_a": "a", "question": "对比两家公司"}
    )
    assert "comparison_workflow 需要 doc_id_a 与 doc_id_b" in " ".join(
        result.get("warnings") or []
    )
    assert result["compare_matrix"] == []
    assert result["compare_highlights"] == []
    assert "未生成第二家公司指标" in result["answer"]
    assert "未配置文档" in result["answer"]
    # Must not invent peer metrics.
    assert "931944638" not in result["answer"]
    assert "差额" not in result["answer"]
