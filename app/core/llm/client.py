from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import PersistenceBackendError


class JsonChatClientProtocol(Protocol):
    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        ...


class JsonChatClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.1,
        timeout: float = 90.0,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "temperature": self._temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        response.raise_for_status()
        choices = response.json().get("choices") or []
        if not choices:
            raise ValueError("LLM response did not contain choices.")
        content = choices[0].get("message", {}).get("content") or ""
        return self._parse_json(content)

    def _parse_json(self, content: str) -> dict[str, Any]:
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("LLM response was not valid JSON.") from None
            payload = json.loads(cleaned[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("LLM JSON response must be an object.")
        return payload


def build_json_chat_client(settings: Settings) -> JsonChatClientProtocol:
    provider = settings.default_llm_provider.strip().lower()
    if provider == "silicon":
        if not settings.silicon_key:
            raise PersistenceBackendError("DEFAULT_LLM_PROVIDER=silicon requires SILICON_KEY.")
        return JsonChatClient(
            api_key=settings.silicon_key,
            base_url=settings.silicon_base_url,
            model=settings.default_llm_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )
    if provider == "openai":
        if not settings.openai_api_key:
            raise PersistenceBackendError("DEFAULT_LLM_PROVIDER=openai requires OPENAI_API_KEY.")
        return JsonChatClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or "https://api.openai.com/v1",
            model=settings.default_llm_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )
    raise PersistenceBackendError(f"Unsupported DEFAULT_LLM_PROVIDER: {provider}")
