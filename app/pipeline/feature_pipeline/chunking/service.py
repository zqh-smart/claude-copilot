from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.claude_copilot.schemas.document import (
    DocumentSegment,
    ParsedDocument,
    ParsedSection,
    ParsedTable,
)


class ChunkingService:
    def __init__(self, chunk_size: int = 800, overlap: int = 100) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, document: ParsedDocument) -> list[DocumentSegment]:
        segments: list[DocumentSegment] = []
        position = 0

        for payload in self._iter_chunk_payloads(document):
            for chunk in self._split_text(payload["content"]):
                if not chunk or not self._has_information(chunk):
                    continue
                position += 1
                segments.append(
                    DocumentSegment(
                        segment_id=f"{document.doc_id}-segment-{position}",
                        document_id=document.doc_id,
                        parent_section_id=payload["parent_section_id"],
                        position=position,
                        content=chunk,
                        content_summary=chunk[:120],
                        keywords=self._extract_keywords(chunk),
                        metadata=payload["metadata"],
                    )
                )

        return segments

    def _iter_chunk_payloads(self, document: ParsedDocument) -> list[dict]:
        payloads: list[dict] = []

        if document.page_blocks:
            for block in document.page_blocks:
                if block.block_type == "table":
                    continue
                content = block.text.strip()
                if not content:
                    continue
                payloads.append(
                    {
                        "content": content,
                        "parent_section_id": block.block_id,
                        "metadata": {
                            "content_type": "page_block",
                            "block_type": block.block_type,
                            "page": block.page,
                            "order": block.order,
                        },
                    }
                )

            for section in document.sections:
                if not section.content.strip():
                    continue
                if section.title and re.fullmatch(r"Page \d+", section.title):
                    continue
                payloads.append(self._section_payload(section))
        else:
            payloads.extend(
                self._section_payload(section)
                for section in document.sections
                if section.content.strip()
            )

        for table in document.tables:
            table_content = (
                self._table_to_text(table)
                if table.headers or table.rows
                else table.raw_markdown or ""
            )
            if not table_content.strip():
                continue
            payloads.append(
                {
                    "content": table_content,
                    "parent_section_id": table.source_block_id or table.table_id,
                    "metadata": {
                        "content_type": "table",
                        "table_type": table.table_type,
                        "page": table.page,
                        "row_count": len(table.rows) + (1 if table.headers else 0),
                        "column_count": len(table.headers),
                    },
                }
            )

        return payloads

    def _section_payload(self, section: ParsedSection) -> dict:
        source = section.metadata.get("source")
        content_type = "semantic_section" if source == "semantic_segmentation" else "section"
        return {
            "content": section.content,
            "parent_section_id": section.section_id,
            "metadata": {
                "content_type": content_type,
                "section_title": section.title,
                "section_type": section.section_type,
                "page_start": section.page_start,
                "page_end": section.page_end,
                "semantic_confidence": section.metadata.get("confidence"),
                "semantic_source": source,
            },
        }

    def _table_to_text(self, table: ParsedTable) -> str:
        rows = []
        if table.headers:
            rows.append(" | ".join(table.headers))
        rows.extend(" | ".join(row) for row in table.rows)
        return "\n".join(rows)

    def _split_text(self, text: str) -> list[str]:
        normalized = self._normalize_content(text)
        if not normalized:
            return []
        if len(normalized) <= self._chunk_size:
            return [normalized]

        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + self._chunk_size, len(normalized))
            chunks.append(normalized[start:end].strip())
            if end >= len(normalized):
                break
            start = max(end - self._overlap, start + 1)
        return chunks

    def _normalize_content(self, text: str) -> str:
        normalized = text.strip()
        if "<table" in normalized.lower() or "<td" in normalized.lower():
            normalized = BeautifulSoup(normalized, "html.parser").get_text(" | ")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    def _has_information(self, text: str) -> bool:
        informative = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
        return len(informative) >= 12

    def _extract_keywords(self, text: str) -> list[str]:
        seen: list[str] = []
        for token in text.replace("\n", " ").split():
            cleaned = token.strip(".,;:()[]{}<>\"'|").lower()
            if len(cleaned) >= 4 and cleaned not in seen:
                seen.append(cleaned)
            if len(seen) >= 8:
                break
        return seen
