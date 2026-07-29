"""Minimal unit tests for agent-chat messages graph helpers."""

from langchain_core.messages import AIMessage, HumanMessage

from app.workflows.agent_chat.graph import _format_answer, _latest_human_text


def test_latest_human_text_reads_last_user_message() -> None:
    messages = [
        HumanMessage(content="first"),
        AIMessage(content="reply"),
        HumanMessage(content="2021年营业收入是多少？"),
    ]
    assert _latest_human_text(messages) == "2021年营业收入是多少？"


def test_format_answer_includes_metrics() -> None:
    class _Preview:
        answer = "营收如下"
        synthesis = None
        metrics = [{"metric_key": "revenue", "period": "2021", "value": 1.0}]
        warnings = ["note"]
        query_analysis = {"intent": "structured", "routes": ["sql"]}

    text = _format_answer(_Preview())
    assert "营收如下" in text
    assert "revenue" in text
    assert "note" in text
