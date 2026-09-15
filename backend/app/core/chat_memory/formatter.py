"""Format MemoryCore recall payloads into bounded prompt fragments."""

from __future__ import annotations

from app.core.chat_memory.models import ChatMemoryBundle, RecalledMemory


def truncate(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.split()).strip()
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max_chars - 1]}…"


def format_recall_context(
    *,
    gateway_context: str,
    memories: list[RecalledMemory],
    max_chars_per_memory: int,
    max_total_chars: int,
) -> str:
    """Prefer gateway ``context`` when present; else build tagged L1 lines."""
    gateway = gateway_context.strip()
    if gateway:
        return truncate(gateway, max_total_chars) if max_total_chars > 0 else gateway

    if not memories:
        return ""

    lines: list[str] = ["<chat-memories>"]
    used = len(lines[0]) + 1
    for item in memories:
        body = truncate(item.content, max_chars_per_memory)
        if not body:
            continue
        label = item.memory_type or "L1"
        line = f"- [{label}] {body}"
        extra = len(line) + 1
        if max_total_chars > 0 and used + extra + len("</chat-memories>") > max_total_chars:
            break
        lines.append(line)
        used += extra
    if len(lines) == 1:
        return ""
    lines.append("</chat-memories>")
    return "\n".join(lines)


def empty_bundle(*warnings: str) -> ChatMemoryBundle:
    return ChatMemoryBundle(warnings=[w for w in warnings if w])
