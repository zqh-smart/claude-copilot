"""Tests for P6 multi-agent orchestrator graph."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from app.workflows.orchestrator.graph import (
    _is_metric_amount_question,
    _route_to_quant_agent,
    _route_to_risk_agent,
    build_orchestrator_graph,
    classify_intent,
    decompose_question,
    format_multi_intent_note,
    select_secondary_intent,
)


def test_route_to_risk_agent_matches_market_risk_question() -> None:
    assert _route_to_risk_agent("公司面临哪些市场风险或风险暴露？") is True
    assert _route_to_risk_agent("2021年营业收入是多少？") is False
    assert _route_to_risk_agent("2021年经营风险相关的营业收入是多少？") is False


def test_route_to_quant_agent_matches_growth_cues() -> None:
    assert _route_to_quant_agent("2021年营收同比增长是多少？") is True
    assert _route_to_quant_agent("过去三年 revenue CAGR 是多少？") is True
    assert _route_to_quant_agent("公司面临哪些市场风险？") is False


def test_is_metric_amount_question() -> None:
    assert _is_metric_amount_question("2021年营业收入是多少？") is True
    assert _is_metric_amount_question("revenue amount for 2021") is True
    assert _is_metric_amount_question("为什么营收增长？") is False


def test_classify_intent_priority() -> None:
    assert classify_intent({"question": "公司面临哪些市场风险？"})["agent_used"] == "risk"
    assert classify_intent({"question": "2021年营收同比增长多少？"})["agent_used"] == "quant"
    assert classify_intent({"question": "2021年营业收入是多少？"})["agent_used"] == "structured"
    assert classify_intent({"question": "管理层如何展望未来？"})["agent_used"] == "research"


def test_decompose_question_splits_multi_clause_intents() -> None:
    assert decompose_question("营收是多少以及有哪些市场风险") == ["risk", "structured"]
    assert decompose_question("2021年营业收入是多少？") == ["structured"]
    assert decompose_question("公司面临哪些市场风险？") == ["risk"]


def test_classify_intent_multi_clause_prefers_higher_priority_agent() -> None:
    result = classify_intent({"question": "2021年营业收入是多少以及有哪些市场风险？"})
    assert result["agent_used"] == "risk"
    assert result["sub_intents"] == ["risk", "structured"]
    assert result["secondary_intent"] == "structured"


def test_select_secondary_intent_picks_safe_specialist() -> None:
    assert select_secondary_intent(["risk", "structured"], "risk") == "structured"
    assert select_secondary_intent(["risk", "quant"], "risk") == "quant"
    # compare / report are not cheap secondaries
    assert select_secondary_intent(["compare", "risk"], "compare") == "risk"
    assert select_secondary_intent(["compare", "report"], "compare") is None


def test_format_multi_intent_note_mentions_secondary_or_suggestions() -> None:
    with_secondary = format_multi_intent_note(
        ["risk", "structured"],
        "risk",
        secondary_ran="structured",
    )
    assert "多意图" in with_secondary
    assert "结构化指标" in with_secondary
    assert "已附带执行次级" in with_secondary

    suggestion_only = format_multi_intent_note(["risk", "compare"], "risk")
    assert "可再问" in suggestion_only
    assert "对比两家公司" in suggestion_only


def test_classify_intent_hybrid_growth_and_amount_prefers_quant() -> None:
    question = "2021年营业收入是多少以及为什么同比增长？"
    result = classify_intent({"question": question})
    assert result["agent_used"] == "quant"
    assert "quant" in result["sub_intents"]
    assert "structured" in result["sub_intents"]


def test_classify_intent_hybrid_causal_and_amount_prefers_research() -> None:
    question = "2021年营业收入是多少以及为什么会出现波动？"
    result = classify_intent({"question": question})
    assert result["agent_used"] == "research"
    assert result["sub_intents"] == ["structured", "research"]


def test_classify_intent_growth_why_without_amount_stays_quant() -> None:
    assert (
        classify_intent({"question": "2021年营业收入相对2020年为什么增长？"})["agent_used"]
        == "quant"
    )


def test_classify_intent_routes_compare_and_report() -> None:
    assert classify_intent({"question": "对比两家公司的营业收入"})["agent_used"] == "compare"
    assert classify_intent({"question": "生成提纲报告"})["agent_used"] == "report"
    assert classify_intent({"question": "年报里有哪些风险"})["agent_used"] == "risk"


def test_default_delegate_compare_missing_doc_id_b_warns() -> None:
    from app.workflows.orchestrator.graph import _default_delegate_compare

    with patch(
        "app.workflows.comparison_workflow.graph.graph.invoke"
    ) as compare_invoke:
        result = _default_delegate_compare(
            {"doc_id": "doc-a", "question": "对比两家公司营收"}
        )

    compare_invoke.assert_not_called()
    assert result["agent_used"] == "compare"
    assert "未配置第二份文档" in result["answer"]
    assert "missing doc_id_b for comparator" in result["warnings"]
    assert "差额" not in result["answer"]


def test_orchestrator_graph_delegates_compare_and_report_with_mocks() -> None:
    calls: dict[str, str] = {}

    def delegate_compare(state: dict[str, Any]) -> dict[str, Any]:
        calls["compare"] = str(state.get("doc_id_b") or "")
        return {"agent_used": "compare", "answer": "compare-answer", "warnings": []}

    def delegate_report(state: dict[str, Any]) -> dict[str, Any]:
        calls["report"] = state["question"]
        return {"agent_used": "report", "answer": "report-answer", "warnings": []}

    compiled = build_orchestrator_graph(
        delegate_compare=delegate_compare,
        delegate_report=delegate_report,
    )
    compare_result = compiled.invoke(
        {
            "doc_id": "doc-a",
            "doc_id_b": "doc-b",
            "question": "对比两家公司营收",
        }
    )
    assert compare_result["agent_used"] == "compare"
    assert compare_result["answer"] == "compare-answer"
    assert calls["compare"] == "doc-b"

    report_result = compiled.invoke(
        {"doc_id": "doc-a", "question": "生成提纲报告"}
    )
    assert report_result["agent_used"] == "report"
    assert report_result["answer"] == "report-answer"
    assert "report" in calls


def test_orchestrator_graph_delegates_with_mocks() -> None:
    calls: dict[str, str] = {}

    def delegate_research(state: dict[str, Any]) -> dict[str, Any]:
        calls["research"] = state["question"]
        return {"agent_used": "research", "answer": "research-answer", "warnings": []}

    def delegate_risk(state: dict[str, Any]) -> dict[str, Any]:
        calls["risk"] = state["question"]
        return {"agent_used": "risk", "answer": "risk-answer", "warnings": ["risk-warn"]}

    def delegate_quant(state: dict[str, Any]) -> dict[str, Any]:
        calls["quant"] = state["question"]
        return {"agent_used": "quant", "answer": "quant-answer", "warnings": []}

    def delegate_structured(state: dict[str, Any]) -> dict[str, Any]:
        calls["structured"] = state["question"]
        return {
            "agent_used": "structured",
            "answer": "structured-answer",
            "warnings": ["metric-warn"],
        }

    compiled = build_orchestrator_graph(
        delegate_research=delegate_research,
        delegate_risk=delegate_risk,
        delegate_quant=delegate_quant,
        delegate_structured=delegate_structured,
    )

    risk_result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "company_id": "co-1",
            "question": "公司面临哪些信用风险？",
            "top_k": 3,
        }
    )
    assert risk_result["agent_used"] == "risk"
    assert risk_result["answer"] == "risk-answer"
    assert risk_result["warnings"] == ["risk-warn"]
    assert "risk" in calls

    quant_result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "question": "营收 CAGR 趋势如何？",
            "top_k": 5,
        }
    )
    assert quant_result["agent_used"] == "quant"
    assert quant_result["answer"] == "quant-answer"
    assert "quant" in calls

    structured_result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "question": "2021年营业收入是多少？",
            "top_k": 5,
        }
    )
    assert structured_result["agent_used"] == "structured"
    assert structured_result["answer"] == "structured-answer"
    assert structured_result["warnings"] == ["metric-warn"]
    assert "structured" in calls

    research_result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "question": "管理层如何分析行业竞争？",
            "top_k": 5,
        }
    )
    assert research_result["agent_used"] == "research"
    assert research_result["answer"] == "research-answer"
    assert "research" in calls
