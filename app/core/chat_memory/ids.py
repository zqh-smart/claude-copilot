"""Resolve session / isolation IDs for MemoryCore requests."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.core.config import Settings, get_settings


def resolve_session_id(
    config: RunnableConfig | None,
    *,
    settings: Settings | None = None,
) -> str:
    cfg = settings or get_settings()
    configurable = (config or {}).get("configurable") or {}
    for key in ("session_id", "thread_id"):
        value = configurable.get(key)
        if value:
            return str(value)
    return f"{cfg.chat_memory_user_id}:default"


def session_key_for(session_id: str, *, settings: Settings | None = None) -> str:
    """MemoryCore /recall and /capture use ``session_key``."""
    cfg = settings or get_settings()
    return f"{cfg.chat_memory_agent_id}:{session_id}"
