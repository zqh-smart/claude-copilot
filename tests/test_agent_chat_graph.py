"""Minimal unit tests for agent-chat messages graph helpers."""

from langchain_core.messages import AIMessage, HumanMessage

from app.workflows.agent_chat.graph import (
    _format_answer,
    _latest_human_text,
    _prefer_primary_metrics,
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
