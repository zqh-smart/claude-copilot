"""Unit tests for Chat Memory local jsonl browse helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.chat_memory.client import HttpChatMemoryClient
from app.core.chat_memory.local_store import (
    is_empty_search_text,
    parse_gateway_search_results,
    read_jsonl_layer,
)
from app.core.config import Settings
import httpx


def test_is_empty_search_text() -> None:
    assert is_empty_search_text("No matching conversation messages found.")
    assert not is_empty_search_text("Found 1 matching message(s):\n---")


def test_parse_gateway_empty_string() -> None:
    assert parse_gateway_search_results(
        "No matching conversation messages found.", layer="L0"
    ) == []


def test_read_jsonl_layer_filters_session(tmp_path: Path) -> None:
    conv = tmp_path / "conversations"
    conv.mkdir()
    rows = [
        {
            "sessionId": "s1",
            "sessionKey": "agent:s1",
            "role": "user",
            "content": "hello s1",
        },
        {
            "sessionId": "s2",
            "sessionKey": "agent:s2",
            "role": "user",
            "content": "hello s2",
        },
    ]
    (conv / "2026-08-04.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    items = read_jsonl_layer(
        tmp_path, subdir="conversations", layer="L0", session_id="s2", limit=10
    )
    assert len(items) == 1
    assert items[0]["content"] == "hello s2"


def test_list_layer_l0_uses_data_dir(tmp_path: Path) -> None:
    conv = tmp_path / "conversations"
    conv.mkdir()
    row = {
        "sessionId": "t1",
        "sessionKey": "agent:t1",
        "role": "user",
        "content": "browse me",
        "id": "m1",
    }
    (conv / "day.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    settings = Settings(
        chat_memory_enabled=True,
        chat_memory_base_url="http://memory.test",
        chat_memory_data_dir=str(tmp_path),
    )
    client = HttpChatMemoryClient(
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )
    result = client.list_layer(layer="L0", limit=10)
    assert result["status"] == "ok"
    assert result["total"] == 1
    assert result["items"][0]["content"] == "browse me"
