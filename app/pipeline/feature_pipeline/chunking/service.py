from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup

from src.claude_copilot.schemas.document import (
    DocumentSegment,
    ParsedDocument,
    ParsedPageBlock,
    ParsedSection,
    ParsedTable,
)


class ChunkingService:
    """Section-aware chunking: semantic sections first, then uncovered blocks/tables."""

    def __init__(self, chunk_size: int = 800, overlap: int = 100) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, document: ParsedDocument) -> list[DocumentSegment]:
        segments: list[DocumentSegment] = []
        position = 0

        for payload in self._iter_chunk_payloads(document):
            chunk_size = payload.get("chunk_size", self._chunk_size)
            for chunk in self._split_text(payload["content"], chunk_size=chunk_size):
                if not chunk or not self._has_information(chunk):
                    continue
                position += 1
                metadata = dict(payload["metadata"])
                metadata["segment_fingerprint"] = self._segment_fingerprint(chunk)
                segments.append(
                    DocumentSegment(
                        segment_id=f"{document.doc_id}-segment-{position}",
                        document_id=document.doc_id,
                        parent_section_id=payload["parent_section_id"],
                        position=position,
                        content=chunk,
                        content_summary=chunk[:120],
                        keywords=self._extract_keywords(chunk),
                        metadata=metadata,
                    )
                )

        return segments

    @staticmethod
    def _segment_fingerprint(content: str) -> str:
        normalized = " ".join(content.split()).casefold()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _iter_chunk_payloads(self, document: ParsedDocument) -> list[dict]:
        payloads: list[dict] = []
        semantic_sections = [
            section
            for section in document.sections
            if section.metadata.get("source") == "semantic_segmentation" and section.content.strip()
        ]
        covered_pages = self._covered_pages(semantic_sections)

        for section in semantic_sections:
            payload = self._section_payload(section)
            # Narrative sections get slightly larger windows.
            if section.section_type in {"management_discussion", "risk_section", "company_overview"}:
                payload["chunk_size"] = max(self._chunk_size, 1200)
            payloads.append(payload)

        if document.page_blocks:
            block_payloads: list[dict] = []
            for block in document.page_blocks:
                if block.block_type in {"table", "header", "footer"}:
                    continue
                if block.page is not None and block.page in covered_pages:
                    continue
                content = block.text.strip()
                if not content or self._is_noise_block(content):
                    continue
                parent = self._nearest_section(block, semantic_sections)
                block_payloads.append(
                    {
                        "content": content,
                        "parent_section_id": parent.section_id if parent else block.block_id,
                        "metadata": {
                            "content_type": "page_block",
                            "block_type": block.block_type,
                            "page": block.page,
                            "order": block.order,
                            "section_type": parent.section_type if parent else None,
                            "section_title": parent.title if parent else None,
                        },
                    }
                )
            payloads.extend(self._coalesce_short_payloads(block_payloads, min_chars=80))
        else:
            for section in document.sections:
                if section.metadata.get("source") == "semantic_segmentation":
                    continue
                if not section.content.strip():
                    continue
                if section.title and re.fullmatch(r"Page \d+", section.title):
                    continue
                payloads.append(self._section_payload(section))

        for table in document.tables:
            table_content = (
                self._table_to_text(table)
                if table.headers or table.rows
                else table.raw_markdown or ""
            )
            if not table_content.strip():
                continue
            parent = self._nearest_section_for_page(table.page, semantic_sections)
            payloads.append(
                {
                    "content": table_content,
                    "parent_section_id": (
                        parent.section_id
                        if parent
                        else table.source_block_id or table.table_id
                    ),
                    "chunk_size": max(self._chunk_size, 1000),
                    "metadata": {
                        "content_type": "table",
                        "table_type": table.table_type,
                        "page": table.page,
                        "row_count": len(table.rows) + (1 if table.headers else 0),
                        "column_count": len(table.headers),
                        "section_type": parent.section_type if parent else table.source_section,
                        "section_title": parent.title if parent else table.title,
                    },
                }
            )

        return payloads

    def _covered_pages(self, sections: list[ParsedSection]) -> set[int]:
        pages: set[int] = set()
        for section in sections:
            if section.page_start is None or section.page_end is None:
                continue
            # Only treat high-confidence, non-tiny sections as coverage owners.
            confidence = float(section.metadata.get("confidence") or 0.0)
            if confidence < 0.9:
                continue
            span = section.page_end - section.page_start
            if span > 40:
                continue
            for page in range(section.page_start, section.page_end + 1):
                pages.add(page)
        return pages

    def _nearest_section(
        self,
        block: ParsedPageBlock,
        sections: list[ParsedSection],
    ) -> ParsedSection | None:
        return self._nearest_section_for_page(block.page, sections)

    def _nearest_section_for_page(
        self,
        page: int | None,
        sections: list[ParsedSection],
    ) -> ParsedSection | None:
        if page is None:
            return None
        matches = [
            section
            for section in sections
            if section.page_start is not None
            and section.page_end is not None
            and section.page_start <= page <= section.page_end
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda section: (
                (section.page_end or page) - (section.page_start or page),
                -(float(section.metadata.get("confidence") or 0.0)),
            )
        )
        return matches[0]

    def _section_payload(self, section: ParsedSection) -> dict:
        source = section.metadata.get("source")
        content_type = "semantic_section" if source == "semantic_segmentation" else "section"
        title_prefix = f"{section.title}\n\n" if section.title else ""
        return {
            "content": f"{title_prefix}{section.content}".strip(),
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
        if table.title:
            rows.append(table.title)
        if table.headers:
            rows.append(" | ".join(table.headers))
        rows.extend(" | ".join(row) for row in table.rows)
        return "\n".join(rows)

    def _split_text(self, text: str, *, chunk_size: int | None = None) -> list[str]:
        size = chunk_size or self._chunk_size
        normalized = self._normalize_content(text)
        if not normalized:
            return []
        if len(normalized) <= size:
            return [normalized]

        # Prefer splitting on paragraph boundaries for section-aware chunks.
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
        if len(paragraphs) >= 2:
            chunks: list[str] = []
            current = ""
            for paragraph in paragraphs:
                candidate = paragraph if not current else f"{current}\n\n{paragraph}"
                if len(candidate) <= size:
                    current = candidate
                    continue
                if current:
                    chunks.append(current)
                if len(paragraph) <= size:
                    current = paragraph
                else:
                    chunks.extend(self._window_split(paragraph, size=size))
                    current = ""
            if current:
                chunks.append(current)
            return chunks

        return self._window_split(normalized, size=size)

    def _window_split(self, text: str, *, size: int) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunks.append(text[start:end].strip())
            if end >= len(text):
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

    def _is_noise_block(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        if len(compact) < 8:
            return True
        if re.fullmatch(r"\d{1,4}", compact):
            return True
        if re.search(r"\.{3,}|…{2,}", text) and len(compact) < 40:
            return True
        if re.match(r"^\d{1,3}第[一二三四五六七八九十百千零〇\d]+[章节]", compact) and len(compact) < 40:
            return True
        return False

    def _coalesce_short_payloads(self, payloads: list[dict], *, min_chars: int) -> list[dict]:
        if not payloads:
            return []
        merged: list[dict] = []
        current = payloads[0]
        for payload in payloads[1:]:
            current_page = current["metadata"].get("page")
            next_page = payload["metadata"].get("page")
            same_parent = current["parent_section_id"] == payload["parent_section_id"]
            page_close = (
                current_page is None
                or next_page is None
                or abs(int(next_page) - int(current_page)) <= 1
            )
            if same_parent and page_close and len(current["content"]) < min_chars:
                current = {
                    **current,
                    "content": f"{current['content']}\n\n{payload['content']}".strip(),
                    "metadata": {
                        **current["metadata"],
                        "block_type": "merged_page_block",
                        "merged_block_count": int(current["metadata"].get("merged_block_count") or 1) + 1,
                    },
                }
                continue
            merged.append(current)
            current = payload
        merged.append(current)
        return [
            item
            for item in merged
            if len(re.sub(r"[\W_]+", "", item["content"], flags=re.UNICODE)) >= 12
        ]

    def _extract_keywords(self, text: str) -> list[str]:
        seen: list[str] = []
        for token in text.replace("\n", " ").split():
            cleaned = token.strip(".,;:()[]{}<>\"'|").lower()
            if len(cleaned) >= 4 and cleaned not in seen:
                seen.append(cleaned)
            if len(seen) >= 8:
                break
        return seen
