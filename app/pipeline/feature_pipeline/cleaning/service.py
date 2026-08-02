"""Document cleaning: headers/footers, TOC noise, and duplicate lines/blocks."""

from __future__ import annotations

import re
from collections import Counter

from src.claude_copilot.schemas.document import ParsedDocument, ParsedPageBlock, ParsedSection


class DocumentCleaningService:
    _TOC_LINE_RE = re.compile(
        r"("
        r"\.{3,}"  # dotted leaders
        r"|…{2,}"
        r"|[\.·•]{2,}\s*\d+\s*$"  # ..... 12
        r"|第[一二三四五六七八九十百千零〇\d]+[章节].*\d+\s*$"
        r")"
    )
    _TOC_TITLE_RE = re.compile(r"^(目录|目\s*录|contents|table of contents)$", re.IGNORECASE)
    _PAGE_ONLY_RE = re.compile(r"^(page\s+\d+|\d+\s*/\s*\d+|\d+)$", re.IGNORECASE)
    _FULLTEXT_HEADER_RE = re.compile(r".{0,40}年年度报告全文\s*$")

    def clean(self, document: ParsedDocument) -> ParsedDocument:
        cleaned = document.model_copy(deep=True)
        if cleaned.page_blocks:
            cleaned.page_blocks = self._clean_page_blocks(cleaned.page_blocks)
        if cleaned.sections:
            cleaned.sections = self._clean_sections(cleaned.sections)
        if cleaned.raw_text:
            cleaned.raw_text = self._clean_raw_text(cleaned.raw_text)
        cleaned.metadata.content_quality_score = cleaned.metadata.content_quality_score
        return cleaned

    def _clean_page_blocks(self, blocks: list[ParsedPageBlock]) -> list[ParsedPageBlock]:
        counts = Counter(self._normalize_for_dedupe(block.text) for block in blocks if block.text.strip())
        repeated_noise = {
            key
            for key, count in counts.items()
            if key and count >= 3 and self._looks_like_marginal_noise(key)
        }
        repeated_long_blocks = {
            key for key, count in counts.items() if key and count >= 2 and len(key) >= 120
        }

        cleaned_blocks: list[ParsedPageBlock] = []
        seen_in_page: dict[int | None, set[str]] = {}
        in_toc = False
        seen_long_blocks: set[str] = set()

        for block in blocks:
            text = block.text.strip()
            if not text:
                continue

            normalized = self._normalize_for_dedupe(text)
            page = block.page

            if block.block_type in {"header", "footer"}:
                continue
            if self._PAGE_ONLY_RE.fullmatch(text):
                continue
            if normalized in repeated_noise:
                continue
            if normalized in repeated_long_blocks:
                if normalized in seen_long_blocks:
                    continue
                seen_long_blocks.add(normalized)
            if self._FULLTEXT_HEADER_RE.search(text) and len(text) <= 60:
                continue
            if self._TOC_TITLE_RE.fullmatch(text):
                in_toc = True
                continue
            if in_toc:
                if self._looks_like_toc_line(text) or block.block_type in {"list_item", "heading"}:
                    # Leave TOC when a substantial narrative paragraph appears.
                    if block.block_type == "paragraph" and len(text) >= 40 and not self._looks_like_toc_line(text):
                        in_toc = False
                    else:
                        continue
                elif len(text) < 80 and re.search(r"\d+\s*$", text):
                    continue
                else:
                    in_toc = False

            if self._looks_like_toc_line(text) and len(text) <= 120:
                continue

            page_seen = seen_in_page.setdefault(page, set())
            if normalized in page_seen:
                continue
            page_seen.add(normalized)

            cleaned_blocks.append(block)

        return cleaned_blocks

    def _clean_sections(self, sections: list[ParsedSection]) -> list[ParsedSection]:
        cleaned: list[ParsedSection] = []
        for section in sections:
            title = (section.title or "").strip()
            if title and self._TOC_TITLE_RE.fullmatch(title):
                continue
            if title and re.fullmatch(r"Page \d+", title):
                continue
            content = self._clean_raw_text(section.content or "")
            if not content.strip():
                continue
            updated = section.model_copy(deep=True)
            updated.content = content
            cleaned.append(updated)
        return cleaned

    def _clean_raw_text(self, text: str) -> str:
        lines = [line.rstrip() for line in text.splitlines()]
        counts = Counter(self._normalize_for_dedupe(line) for line in lines if line.strip())
        repeated = {
            key
            for key, count in counts.items()
            if key and count >= 3 and self._looks_like_marginal_noise(key)
        }
        repeated_long_lines = {
            key for key, count in counts.items() if key and count >= 2 and len(key) >= 120
        }

        kept: list[str] = []
        prev_norm = ""
        seen_long_lines: set[str] = set()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if kept and kept[-1] != "":
                    kept.append("")
                continue
            normalized = self._normalize_for_dedupe(stripped)
            if normalized in repeated or self._PAGE_ONLY_RE.fullmatch(stripped):
                continue
            if normalized in repeated_long_lines:
                if normalized in seen_long_lines:
                    continue
                seen_long_lines.add(normalized)
            if self._FULLTEXT_HEADER_RE.search(stripped) and len(stripped) <= 60:
                continue
            if self._looks_like_toc_line(stripped) and len(stripped) <= 120:
                continue
            if normalized == prev_norm:
                continue
            kept.append(stripped)
            prev_norm = normalized
        return "\n".join(kept).strip()

    def _looks_like_toc_line(self, text: str) -> bool:
        if self._TOC_LINE_RE.search(text):
            return True
        # "第一节 xxx........ 2"
        return bool(re.search(r"第[一二三四五六七八九十百千零〇\d]+[章节].{0,40}\d+\s*$", text))

    def _looks_like_marginal_noise(self, normalized: str) -> bool:
        if len(normalized) <= 80 and (
            "年度报告全文" in normalized
            or "年年度报告" in normalized
            or "annualreport" in normalized
            or "form#-k" in normalized
            or self._PAGE_ONLY_RE.fullmatch(normalized)
        ):
            return True
        return len(normalized) <= 40 and normalized.isdigit()

    def _normalize_for_dedupe(self, text: str) -> str:
        normalized = re.sub(r"\s+", "", text.strip().lower())
        normalized = re.sub(r"\d+", "#", normalized)
        return normalized
