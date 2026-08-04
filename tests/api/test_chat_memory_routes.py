"""FastAPI chat-memory proxy routes (Workbench; not document KG)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_chat_memory_client
from app.core.chat_memory import NoopChatMemory
from app.main import app

client = TestClient(app)


def test_chat_memory_health_disabled_by_default() -> None:
    app.dependency_overrides[get_chat_memory_client] = lambda: NoopChatMemory()
    try:
        response = client.get("/api/v1/chat-memory/health")
    finally:
        app.dependency_overrides.pop(get_chat_memory_client, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"disabled", "down", "up"}
    assert "base_url" in payload


def test_chat_memory_layers_uses_client() -> None:
    fake = MagicMock()
    fake.list_layer.return_value = {
        "layer": "L1",
        "items": [{"id": "a", "content": "prefers CNY"}],
        "total": 1,
        "status": "ok",
        "warnings": [],
    }
    app.dependency_overrides[get_chat_memory_client] = lambda: fake
    try:
        response = client.get("/api/v1/chat-memory/layers/L1?limit=10")
    finally:
        app.dependency_overrides.pop(get_chat_memory_client, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["layer"] == "L1"
    assert payload["items"][0]["content"] == "prefers CNY"
    fake.list_layer.assert_called_once()


def test_chat_memory_search_requires_query() -> None:
    response = client.get("/api/v1/chat-memory/search")
    assert response.status_code == 422


def test_chat_memory_search_ok() -> None:
    fake = MagicMock()
    fake.search.return_value = {
        "items": [{"content": "hit"}],
        "total": 1,
        "status": "ok",
        "warnings": [],
    }
    app.dependency_overrides[get_chat_memory_client] = lambda: fake
    try:
        response = client.get("/api/v1/chat-memory/search", params={"q": "营收"})
    finally:
        app.dependency_overrides.pop(get_chat_memory_client, None)
    assert response.status_code == 200
    assert response.json()["items"][0]["content"] == "hit"


def test_chat_memory_capture_when_enabled() -> None:
    fake = MagicMock()
    app.dependency_overrides[get_chat_memory_client] = lambda: fake
    try:
        with patch("app.api.v1.chat_memory.get_settings") as get_settings:
            settings = MagicMock()
            settings.chat_memory_enabled = True
            settings.chat_memory_capture_enabled = True
            get_settings.return_value = settings
            response = client.post(
                "/api/v1/chat-memory/capture",
                json={
                    "session_id": "s1",
                    "user_text": "hello",
                    "assistant_text": "world",
                },
            )
    finally:
        app.dependency_overrides.pop(get_chat_memory_client, None)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    fake.capture.assert_called_once()


def test_chat_memory_capture_rejected_when_disabled() -> None:
    fake = MagicMock()
    app.dependency_overrides[get_chat_memory_client] = lambda: fake
    try:
        with patch("app.api.v1.chat_memory.get_settings") as get_settings:
            settings = MagicMock()
            settings.chat_memory_enabled = False
            settings.chat_memory_capture_enabled = True
            get_settings.return_value = settings
            response = client.post(
                "/api/v1/chat-memory/capture",
                json={
                    "session_id": "s1",
                    "user_text": "hello",
                    "assistant_text": "world",
                },
            )
    finally:
        app.dependency_overrides.pop(get_chat_memory_client, None)
    assert response.status_code == 503
    fake.capture.assert_not_called()
