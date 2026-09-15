"""Tests for agent-chat MemoryCore recall/capture wiring."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.core.chat_memory.formatter import format_recall_context
from app.core.chat_memory.models import ChatMemoryBundle, RecalledMemory
from app.core.chat_memory.noop import NoopChatMemory
from app.workflows.agent_chat.graph import (
    capture_chat_memory,
    recall_chat_memory,
    research_turn,
)


def test_format_recall_context_prefers_gateway_context() -> None:
    text = format_recall_context(
        gateway_context="persona notes",
        memories=[RecalledMemory(content="ignored")],
        max_chars_per_memory=400,
        max_total_chars=2000,
    )
    assert text == "persona notes"


def test_format_recall_context_builds_tagged_lines() -> None:
    text = format_recall_context(
        gateway_context="",
        memories=[RecalledMemory(content="偏好简洁回答", memory_type="preference")],
        max_chars_per_memory=400,
        max_total_chars=2000,
    )
    assert "<chat-memories>" in text
    assert "偏好简洁回答" in text


def test_noop_recall_and_capture() -> None:
    client = NoopChatMemory()
    assert client.health()["status"] == "disabled"
    assert client.recall(query="q", session_id="s").prepend == ""
    client.capture(session_id="s", user_text="u", assistant_text="a")


def test_recall_chat_memory_writes_prepend() -> None:
    fake = MagicMock()
    fake.recall.return_value = ChatMemoryBundle(
        prepend="<chat-memories>\n- hi\n</chat-memories>",
        warnings=[],
    )
    with patch("app.api.dependencies.get_chat_memory_client", return_value=fake):
        out = recall_chat_memory(
            {"messages": [HumanMessage(content="营收多少？")]},
            {"configurable": {"thread_id": "thread-1"}},
        )
    assert out["chat_memory_prepend"]
    assert out["chat_memory_session_id"] == "thread-1"
    fake.recall.assert_called_once()
    assert fake.recall.call_args.kwargs["query"] == "营收多少？"


def test_recall_timeout_does_not_raise() -> None:
    fake = MagicMock()
    fake.recall.return_value = ChatMemoryBundle(warnings=["recall_failed: TimeoutException"])
    with patch("app.api.dependencies.get_chat_memory_client", return_value=fake):
        out = recall_chat_memory(
            {"messages": [HumanMessage(content="q")]},
            {"configurable": {"thread_id": "t"}},
        )
    assert out["chat_memory_prepend"] is None
    assert out["chat_memory_warnings"]


def test_research_turn_passes_clean_question_and_memory_context() -> None:
    class _Record:
        class metadata:
            company = "指南针"

    seen: dict[str, Any] = {}

    def fake_invoke(**kwargs: Any) -> str:
        seen.update(kwargs)
        return "ok"

    with (
        patch("app.workflows.agent_chat.graph._resolve_doc_id", return_value="doc-1"),
        patch("app.workflows.agent_chat.graph._resolve_doc_id_b", return_value=None),
        patch("app.api.dependencies.get_document_pipeline_service") as get_pipeline,
        patch(
            "app.workflows.agent_chat.graph._invoke_chat_specialist",
            side_effect=fake_invoke,
        ),
    ):
        get_pipeline.return_value.get_document.return_value = _Record()
        research_turn(
            {
                "messages": [HumanMessage(content="2021年营业收入是多少？")],
                "chat_memory_prepend": "<chat-memories>\n- prefer CNY\n</chat-memories>",
            },
            {},
        )
    assert seen["question"] == "2021年营业收入是多少？"
    assert seen["chat_memory_context"] and "prefer CNY" in seen["chat_memory_context"]


def test_capture_uses_clean_user_text() -> None:
    fake = MagicMock()
    with patch("app.api.dependencies.get_chat_memory_client", return_value=fake):
        capture_chat_memory(
            {
                "messages": [
                    HumanMessage(content="原始问题"),
                    AIMessage(content="答案正文"),
                ],
                "chat_memory_session_id": "sess-9",
                "doc_id": "doc-1",
            },
            {},
        )
    fake.capture.assert_called_once()
    kwargs = fake.capture.call_args.kwargs
    assert kwargs["session_id"] == "sess-9"
    assert kwargs["user_text"] == "原始问题"
    assert kwargs["assistant_text"] == "答案正文"
    assert "chat-memories" not in kwargs["user_text"]
