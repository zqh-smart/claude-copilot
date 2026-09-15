from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.core.llm.client import JsonChatClient


def _client_with_response(payload: dict[str, Any]) -> JsonChatClient:
    client = JsonChatClient(
        api_key="test-key",
        base_url="http://example.local/v1",
        model="qwen3.5",
    )
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    client._client.post = MagicMock(return_value=response)  # type: ignore[method-assign]
    return client


def test_complete_json_disables_thinking_and_parses_content() -> None:
    client = _client_with_response(
        {
            "choices": [
                {"message": {"role": "assistant", "content": '{"answer":"ok"}'}},
            ]
        }
    )
    result = client.complete_json(system_prompt="sys", user_prompt="user")
    assert result == {"answer": "ok"}
    posted = client._client.post.call_args.kwargs["json"]
    assert posted["chat_template_kwargs"] == {"enable_thinking": False}


def test_json_chat_client_disables_env_proxy() -> None:
    client = JsonChatClient(
        api_key="test-key",
        base_url="http://example.local/v1",
        model="qwen3.5",
    )
    assert client._client._trust_env is False


def test_complete_json_falls_back_to_reasoning_content() -> None:
    client = _client_with_response(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_content": '{"answer":"from-reasoning"}',
                    }
                }
            ]
        }
    )
    result = client.complete_json(system_prompt="sys", user_prompt="user")
    assert result == {"answer": "from-reasoning"}
