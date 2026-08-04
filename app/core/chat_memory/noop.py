"""No-op chat memory when sidecar is disabled or unavailable by config."""

from __future__ import annotations

from typing import Any, Literal

from app.core.chat_memory.models import ChatMemoryBundle

MemoryLayer = Literal["L0", "L1", "L2", "L3"]


class NoopChatMemory:
    def __init__(self, *, reason: str = "chat_memory_disabled") -> None:
        self._reason = reason

    def health(self) -> dict[str, Any]:
        return {"status": "disabled", "reason": self._reason}

    def recall(self, *, query: str, session_id: str | None) -> ChatMemoryBundle:
        del query, session_id
        return ChatMemoryBundle()

    def capture(
        self,
        *,
        session_id: str,
        user_text: str,
        assistant_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        del session_id, user_text, assistant_text, metadata

    def list_layer(
        self,
        *,
        layer: MemoryLayer,
        session_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        del session_id, limit, offset
        return {
            "layer": layer,
            "items": [],
            "total": 0,
            "status": "disabled",
            "reason": self._reason,
            "warnings": [],
        }

    def search(
        self,
        *,
        query: str,
        limit: int = 20,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        del query, limit, session_id
        return {
            "items": [],
            "total": 0,
            "status": "disabled",
            "reason": self._reason,
            "warnings": [],
        }