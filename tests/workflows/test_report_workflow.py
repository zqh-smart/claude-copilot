from app.workflows.report_workflow.graph import (
    build_report_workflow_graph,
    compose_report_workflow_answer,
)


def test_compose_report_workflow_answer_sections() -> None:
    text = compose_report_workflow_answer(
        report_answer="## 核心财务指标\n- revenue",
        quant_summary="- revenue：YoY 2021=10.00%",
        warnings=["风险检索降级"],
    )
    assert "§5.5" in text
    assert "提纲正文" in text
    assert "增长快照" in text
    assert "YoY 2021=10.00%" in text
    assert "风险检索降级" in text
    assert "无 PDF" in text


def test_report_workflow_graph_with_injected_steps() -> None:
    def prepare(state: dict) -> dict:
        return {"warnings": []}

    def report(_state: dict) -> dict:
        return {
            "report_answer": "提纲：营收与风险",
            "report_sections": [{"title": "核心财务指标", "bullets": ["revenue"]}],
            "calculations": [
                {
                    "metric_key": "revenue",
                    "yoy_growth": {2021: 0.1},
                    "cagr": 0.1,
                }
            ],
        }

    def quant(state: dict) -> dict:
        calcs = list(state.get("calculations") or [])
        assert calcs
        return {"quant_summary": "- revenue：YoY 2021=10.00%"}

    graph = build_report_workflow_graph(
        prepare_fn=prepare,
        report_fn=report,
        quant_fn=quant,
    )
    result = graph.invoke({"doc_id": "doc-1", "question": "生成提纲报告"})
    assert "§5.5" in result["answer"]
    assert "提纲：营收与风险" in result["answer"]
    assert "YoY 2021=10.00%" in result["answer"]
