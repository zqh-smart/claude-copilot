"""Unit tests for HttpChatMemoryClient (no live MemoryCore)."""

from __future__ import annotations

import httpx

from app.core.chat_memory.client import HttpChatMemoryClient
from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    base = {
        "chat_memory_enabled": True,
        "chat_memory_base_url": "http://memory.test",
        "chat_memory_service_id": "svc",
        "chat_memory_team_id": "team",
        "chat_memory_agent_id": "agent",
        "chat_memory_user_id": "user",
        "chat_memory_recall_timeout_ms": 1000,
        "chat_memory_recall_max_results": 5,
        "chat_memory_capture_enabled": True,
        "chat_memory_max_chars_per_memory": 400,
        "chat_memory_max_total_recall_chars": 2000,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_recall_parses_gateway_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/recall"
        return httpx.Response(
            200,
            json={"context": "remember CNY", "strategy": "hybrid", "memory_count": 1, "code": 0},
        )

    transport = httpx.MockTransport(handler)
    client = HttpChatMemoryClient(
        settings=_settings(),
        client=httpx.Client(transport=transport),
    )
    bundle = client.recall(query="营收", session_id="t1")
    assert "remember CNY" in bundle.prepend
    assert bundle.strategy == "hybrid"


def test_recall_failure_returns_empty_bundle() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    transport = httpx.MockTransport(handler)
    client = HttpChatMemoryClient(
        settings=_settings(),
        client=httpx.Client(transport=transport),
    )
    bundle = client.recall(query="q", session_id="t1")
    assert bundle.prepend == ""
    assert bundle.warnings


def test_capture_posts_clean_turn() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["json"] = httpx.Request(
            request.method, request.url, content=request.content, headers=request.headers
        )
        import json

        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"l0_recorded": 1})

    transport = httpx.MockTransport(handler)
    client = HttpChatMemoryClient(
        settings=_settings(),
        client=httpx.Client(transport=transport),
    )
    client.capture(session_id="s1", user_text="hello", assistant_text="world")
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["user_content"] == "hello"
    assert body["assistant_content"] == "world"
    assert body["session_id"] == "s1"
