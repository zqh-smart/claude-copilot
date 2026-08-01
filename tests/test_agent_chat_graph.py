"""Minimal unit tests for agent-chat messages graph helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from app.workflows.agent_chat.graph import (
    _format_answer,
    _invoke_chat_specialist,
    _latest_human_text,
    _prefer_primary_metrics,
    research_turn,
)
from app.workflows.orchestrator.graph import classify_intent


def test_latest_human_text_reads_last_user_message() -> None:
    messages = [
        HumanMessage(content="first"),
        AIMessage(content="reply"),
        HumanMessage(content="2021年营业收入是多少？"),
    ]
    assert _latest_human_text(messages) == "2021年营业收入是多少？"


def test_prefer_primary_metrics_keeps_larger_value() -> None:
    rows = [
        ("revenue", "2021", 4.35),
        ("revenue", "2021", 469378042.95),
    ]
    preferred = _prefer_primary_metrics(rows)
    assert preferred == [("revenue", "2021", 469378042.95)]


def test_format_answer_prefers_primary_when_llm_fails() -> None:
    class _Preview:
        answer = "revenue(2021)=4.35；revenue(2021)=469378042.95"
        synthesis = None
        metrics = [
            {"metric_key": "revenue", "period": "2021", "value": 4.35},
            {"metric_key": "revenue", "period": "2021", "value": 469378042.95},
        ]
        warnings = [
            "grounded synthesis failed: Server error '502 Bad Gateway' for url 'http://192.168.0.102:30000/v1/chat/completions'"
        ]
        query_analysis = {"intent": "structured", "routes": ["sql"]}

    text = _format_answer(_Preview())
    assert "469378042.95" in text
    assert "4.35" not in text
    assert "本地 LLM 暂时不可用" in text


def test_format_answer_includes_fusion_summary() -> None:
    class _Fusion:
        query_intent = "hybrid"
        routes = ["vector", "sql"]
        summary = "意图=hybrid，启用通道：语义片段 + 结构化指标。"
        highlights = ["[结构化] revenue 2021 = 931944638"]

    class _Preview:
        answer = ""
        synthesis = None
        metrics = [{"metric_key": "revenue", "period": "2021", "value": 931944638}]
        warnings = ["grounded synthesis failed: HTTPStatusError 502"]
        query_analysis = {"intent": "hybrid", "routes": ["vector", "sql"]}
        fusion_summary = _Fusion()

    text = _format_answer(_Preview())
    assert "混合检索摘要" in text
    assert "931944638" in text
    assert "intent=hybrid" not in text


def test_classify_intent_routes_market_risk_question() -> None:
    assert classify_intent({"question": "公司面临哪些市场风险或风险暴露？"})["agent_used"] == "risk"
    assert classify_intent({"question": "2021年营业收入是多少？"})["agent_used"] == "structured"
    assert classify_intent({"question": "2021年营业收入相对2020年为什么增长？"})["agent_used"] == "quant"
    assert classify_intent({"question": "对比两家公司的营业收入"})["agent_used"] == "compare"
    assert classify_intent({"question": "生成提纲报告"})["agent_used"] == "report"


def test_research_turn_runs_secondary_specialist_for_multi_intent() -> None:
    class _Record:
        class metadata:
            company = "指南针"

    calls: list[str] = []

    def fake_invoke(*, agent_used: str, question: str, **_kwargs: Any) -> str:
        calls.append(agent_used)
        return f"{agent_used}-block for {question[:8]}"

    with (
        patch(
            "app.workflows.agent_chat.graph._resolve_doc_id",
            return_value="doc-1",
        ),
        patch(
            "app.workflows.agent_chat.graph._resolve_doc_id_b",
            return_value=None,
        ),
        patch(
            "app.api.dependencies.get_document_pipeline_service"
        ) as get_pipeline,
        patch(
            "app.workflows.agent_chat.graph._invoke_chat_specialist",
            side_effect=fake_invoke,
        ),
    ):
        get_pipeline.return_value.get_document.return_value = _Record()
        result = research_turn(
            {
                "messages": [
                    HumanMessage(content="2021年营业收入是多少以及有哪些市场风险？")
                ]
            },
            {},
        )

    assert calls == ["risk", "structured"]
    text = str(result["messages"][0].content)
    assert "risk-block" in text
    assert "次级 · structured" in text
    assert "多意图" in text
    assert "已附带执行次级" in text


def test_compare_without_doc_id_b_warns_and_skips_workflow() -> None:
    """Missing second doc must be an explicit warning — never invent company B."""
    with patch(
        "app.workflows.comparison_workflow.graph.graph.invoke"
    ) as compare_invoke:
        answer = _invoke_chat_specialist(
            agent_used="compare",
            question="对比两家公司的营业收入",
            doc_id="doc-a",
            doc_id_b=None,
            company_id=None,
        )

    compare_invoke.assert_not_called()
    assert "未配置第二份文档" in answer
    assert "AGENT_CHAT_DOC_ID_B" in answer
    assert "doc_id_b" in answer
    # No fabricated peer metrics / company names.
    assert "营业收入" not in answer or "未配置" in answer
    assert "931944638" not in answer
    assert "差额" not in answer
