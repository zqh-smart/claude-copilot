"""Contextual Retrieval prefixes for embedding/indexing (Anthropic-style)."""

from __future__ import annotations

from src.claude_copilot.schemas.document import ParsedDocument


def build_contextual_prefix(
    document: ParsedDocument,
    *,
    section_title: str | None,
    section_type: str | None,
    page: int | None = None,
) -> str:
    meta = document.metadata
    company = meta.company or "未知公司"
    year = meta.year
    doc_label = meta.filename or document.doc_id
    lines = [
        f"公司：{company}",
        f"文档：{doc_label}",
    ]
    if year is not None:
        lines.append(f"年份：{year}")
    if section_type:
        lines.append(f"章节类型：{section_type}")
    if section_title:
        lines.append(f"章节：{section_title}")
    if page is not None:
        lines.append(f"页码：{page}")
    lines.append("正文：")
    return "\n".join(lines)


def apply_contextual_prefix(content: str, prefix: str) -> str:
    body = content.strip()
    if not body:
        return body
    if body.startswith(prefix.splitlines()[0]):
        return body
    return f"{prefix}\n{body}"
