"""Chat-memory DTOs (MemoryCore sidecar; not document KG)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecalledMemory:
    content: str
    score: float | None = None
    memory_type: str | None = None


@dataclass
class ChatMemoryBundle:
    """Prompt fragments from MemoryCore recall.

    ``prepend`` is injected near the user turn for synthesis only.
    Retrieval / intent routing must keep using the clean user question.
    """

    prepend: str = ""
    append: str = ""
    memories: list[RecalledMemory] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    strategy: str | None = None
    memory_count: int = 0

    @property
    def context_text(self) -> str:
        parts = [part for part in (self.prepend, self.append) if part.strip()]
        return "\n\n".join(parts).strip()
