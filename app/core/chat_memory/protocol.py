"""Protocol for Chat memory (MemoryCore sidecar)."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from app.core.chat_memory.models import ChatMemoryBundle

MemoryLayer = Literal["L0", "L1", "L2", "L3"]


class ChatMemoryProtocol(Protocol):
    def health(self) -> dict[str, Any]:
        """Return sidecar health payload; must not raise to callers of recall/capture."""

    def recall(self, *, query: str, session_id: str | None) -> ChatMemoryBundle:
        """Prefetch L1/L2/L3 context. Failures return an empty bundle with warnings."""

    def capture(
        self,
        *,
        session_id: str,
        user_text: str,
        assistant_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one turn to L0. Failures are swallowed (logged via warnings/logger)."""

    def list_layer(
        self,
        *,
        layer: MemoryLayer,
        session_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Browse one memory layer for Workbench UI."""

    def search(
        self,
        *,
        query: str,
        limit: int = 20,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Search L1 (and fallback gateway search) for Workbench UI."""