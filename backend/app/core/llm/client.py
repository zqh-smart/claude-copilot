from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import PersistenceBackendError

logger = logging.getLogger(__name__)


class JsonChatClientProtocol(Protocol):
    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]: ...


class JsonChatClient:
    _RATE_LIMIT_DELAYS = (5.0, 15.0, 30.0)

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.1,
        timeout: float = 90.0,
        enable_thinking: bool | None = None,
        max_tokens: int | None = None,
        include_chat_template_kwargs: bool = True,
        rate_limit_delays: tuple[float, ...] | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._enable_thinking = enable_thinking
        self._max_tokens = max_tokens
        self._include_chat_template_kwargs = include_chat_template_kwargs
        self._rate_limit_delays = (
            self._RATE_LIMIT_DELAYS if rate_limit_delays is None else rate_limit_delays
        )
        self._rate_limit_retry_count = 0
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            trust_env=False,
        )

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        request_payload: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self._include_chat_template_kwargs:
            # Local qwen3.5 thinking models otherwise leave content null.
            request_payload["chat_template_kwargs"] = {"enable_thinking": False}
        if self._enable_thinking is not None:
            request_payload["enable_thinking"] = self._enable_thinking
        if self._max_tokens is not None:
            request_payload["max_tokens"] = self._max_tokens
        response = self._post_with_rate_limit_retry(request_payload)
        choices = response.json().get("choices") or []
        if not choices:
            raise ValueError("LLM response did not contain choices.")
        message = choices[0].get("message") or {}
        content = message.get("content") or message.get("reasoning_content") or ""
        return self._parse_json(content)

    @property
    def rate_limit_retry_count(self) -> int:
        return self._rate_limit_retry_count

    @property
    def model(self) -> str:
        return self._model

    def _post_with_rate_limit_retry(self, request_payload: dict[str, Any]) -> httpx.Response:
        for attempt in range(len(self._rate_limit_delays) + 1):
            response = self._client.post("/chat/completions", json=request_payload)
            try:
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError:
                if response.status_code != 429 or attempt == len(self._rate_limit_delays):
                    raise
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else None
                except ValueError:
                    delay = None
                delay = self._rate_limit_delays[attempt] if delay is None else delay
                self._rate_limit_retry_count += 1
                time.sleep(min(max(delay, 0.0), 60.0))
        raise RuntimeError("unreachable rate-limit retry state")

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


class FailoverJsonChatClient:
    """Use the first healthy model and retain it until a later request fails."""

    def __init__(self, clients: list[JsonChatClient]) -> None:
        if not clients:
            raise ValueError("At least one JSON chat client is required.")
        self._clients = clients
        self._active_index = 0

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        order = list(range(self._active_index, len(self._clients))) + list(
            range(self._active_index)
        )
        last_error: Exception | None = None
        for index in order:
            client = self._clients[index]
            try:
                result = client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "LLM model %s failed; trying the next configured model (%s).",
                    client.model,
                    type(exc).__name__,
                )
                continue
            self._active_index = index
            return result
        self._active_index = 0
        if last_error is not None:
            raise last_error
        raise RuntimeError("No LLM model was attempted.")

    @property
    def active_model(self) -> str:
        return self._clients[self._active_index].model

    @property
    def rate_limit_retry_count(self) -> int:
        return sum(client.rate_limit_retry_count for client in self._clients)


def build_json_chat_client(settings: Settings) -> JsonChatClientProtocol:
    api_type = settings.llm_model_api_type.strip().lower()
    if api_type == "openai":
        if not settings.llm_model_api_key:
            raise PersistenceBackendError("LLM_MODEL_API_TYPE=openai requires LLM_MODEL_API_KEY.")
        return JsonChatClient(
            api_key=settings.llm_model_api_key,
            base_url=settings.llm_model_base_url,
            model=settings.llm_model_name,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )
    if api_type == "silicon":
        if not settings.silicon_key:
            raise PersistenceBackendError("LLM_MODEL_API_TYPE=silicon requires SILICON_KEY.")
        return JsonChatClient(
            api_key=settings.silicon_key,
            base_url=settings.silicon_base_url,
            model=settings.llm_model_name,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
            enable_thinking=False,
            max_tokens=2048,
        )
    if api_type == "bailian":
        if not settings.bailian_api_key:
            raise PersistenceBackendError(
                "LLM_MODEL_API_TYPE=bailian requires BAI_LIAN_API_KEY, "
                "BAILIAN_API_KEY, or DASHSCOPE_API_KEY."
            )
        model_names = [settings.llm_model_name]
        model_names.extend(
            model.strip()
            for model in settings.bailian_fallback_models.split(",")
            if model.strip() and model.strip() not in model_names
        )
        clients = [
            JsonChatClient(
                api_key=settings.bailian_api_key,
                base_url=settings.bailian_base_url,
                model=model,
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout_seconds,
                enable_thinking=False,
                max_tokens=4096,
                include_chat_template_kwargs=False,
                rate_limit_delays=(),
            )
            for model in model_names
        ]
        return FailoverJsonChatClient(clients)
    raise PersistenceBackendError(f"Unsupported LLM_MODEL_API_TYPE: {api_type}")
