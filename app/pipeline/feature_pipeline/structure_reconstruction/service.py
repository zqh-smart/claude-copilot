from __future__ import annotations

import re

from src.claude_copilot.schemas.document import ParsedDocument, ParsedPageBlock, ParsedSection, ParsedTable


class StructureReconstructionService:
    _PRIMARY_STATEMENT_PATTERNS: dict[str, tuple[str, ...]] = {
        "income_statement": (
            "statements of income",
            "statement of income",
            "income statement",
            "statements of earnings",
            "statement of earnings",
            "comprehensive income",
            "statement of operations",
        ),
        "balance_sheet": (
            "balance sheets",
            "balance sheet",
        ),
        "cash_flow": (
            "cash flows",
            "cash flow",
            "net cash provided by operating activities",
        ),
        "equity": (
            "stockholders' equity",
            "shareholders' equity",
            "changes in stockholders",
            "changes in equity",
        ),
    }

    def reconstruct(self, document: ParsedDocument) -> ParsedDocument:
        if not document.tables:
            return document

        semantic_sections = [
            section for section in document.sections if section.metadata.get("source") == "semantic_segmentation"
        ]
        note_sections = [section for section in semantic_sections if section.section_type == "financial_note"]

        document.tables = [
            self._refine_table(
                table,
                note_sections=note_sections,
                semantic_sections=semantic_sections,
                page_blocks=document.page_blocks,
                single_logical_page=document.metadata.page_count == 1,
            )
            for table in document.tables
        ]
        return document

    def _refine_table(
        self,
        table: ParsedTable,
        *,
        note_sections: list[ParsedSection],
        semantic_sections: list[ParsedSection],
        page_blocks: list[ParsedPageBlock],
        single_logical_page: bool,
    ) -> ParsedTable:
        refined = table.model_copy(deep=True)
        attached_note = self._select_attached_note_section(
            table=refined,
            note_sections=note_sections,
            page_blocks=page_blocks,
            single_logical_page=single_logical_page,
        )
        if attached_note is not None:
            refined.source_section = "financial_note"
            refined.metadata["source_section_id"] = attached_note.section_id
            refined.metadata["source_section_title"] = attached_note.title
            refined.metadata["structure_reconstruction"] = "note_attachment"

            note_number, note_title = self._parse_note_heading(attached_note.title or "")
            if note_number and not refined.note_number:
                refined.note_number = note_number
            if note_title and not refined.note_title:
                refined.note_title = note_title
            if not refined.title or self._is_generic_notes_title(refined.title):
                refined.title = attached_note.title

            if refined.table_type in self._PRIMARY_STATEMENT_PATTERNS and not self._looks_like_primary_statement(refined):
                refined.table_type = "notes_table"

        if refined.table_type == "notes_table" and not refined.note_number and not refined.note_title:
            fallback_number, fallback_title = self._parse_note_heading(
                str(refined.metadata.get("source_section_title") or refined.title or "")
            )
            if fallback_number:
                refined.note_number = fallback_number
            if fallback_title:
                refined.note_title = fallback_title

        statement_section = self._find_statement_section(table=refined, semantic_sections=semantic_sections)
        if statement_section and refined.source_section != "financial_note":
            refined.source_section = statement_section.section_type
            refined.metadata["source_section_id"] = statement_section.section_id
            refined.metadata["source_section_title"] = statement_section.title

        return refined

    def _select_attached_note_section(
        self,
        *,
        table: ParsedTable,
        note_sections: list[ParsedSection],
        page_blocks: list[ParsedPageBlock],
        single_logical_page: bool,
    ) -> ParsedSection | None:
        if table.page is None or not note_sections:
            return None
        if single_logical_page and not re.match(
            r"^(?:notes?\s+to\b|note\s+\d+)",
            self._normalize_text(table.title or ""),
        ):
            return None

        order_lookup = {block.block_id: block.order for block in page_blocks if block.block_id}
        table_order = order_lookup.get(table.source_block_id)
        if table_order is not None:
            ordered_candidates = [
                section
                for section in note_sections
                if section.page_start == table.page
                and order_lookup.get(section.metadata.get("anchor_block_id")) is not None
                and (order_lookup.get(section.metadata.get("anchor_block_id")) or 0) <= table_order
            ]
            if ordered_candidates:
                ordered_candidates.sort(
                    key=lambda section: table_order
                    - (order_lookup.get(section.metadata.get("anchor_block_id")) or 0)
                )
                return ordered_candidates[0]
            # HTML and DOCX may represent the whole document as one logical page.
            # In that case, a later note heading must not capture an earlier table.
            if sum(1 for block in page_blocks if block.page == table.page) > 1:
                return None

        exact_matches = [
            section
            for section in note_sections
            if section.page_start is not None
            and section.page_end is not None
            and section.page_start <= table.page <= section.page_end
        ]
        if exact_matches:
            exact_matches.sort(key=lambda section: (section.page_end or table.page) - (section.page_start or table.page))
            return exact_matches[0]

        prior_candidates = [
            section
            for section in note_sections
            if section.page_start is not None and section.page_start <= table.page and table.page - section.page_start <= 8
        ]
        if prior_candidates:
            prior_candidates.sort(key=lambda section: table.page - (section.page_start or table.page))
            return prior_candidates[0]

        next_candidates = [
            section
            for section in note_sections
            if section.page_start is not None and 0 < (section.page_start - table.page) <= 2
        ]
        if next_candidates and self._is_generic_notes_title(table.title):
            next_candidates.sort(key=lambda section: (section.page_start or table.page) - table.page)
            return next_candidates[0]

        return None

    def _find_statement_section(
        self,
        *,
        table: ParsedTable,
        semantic_sections: list[ParsedSection],
    ) -> ParsedSection | None:
        if table.page is None:
            return None
        candidates = [
            section
            for section in semantic_sections
            if section.section_type == "financial_statement"
            and section.page_start is not None
            and section.page_end is not None
            and section.page_start <= table.page <= section.page_end
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda section: (section.page_end or table.page) - (section.page_start or table.page))
        return candidates[0]

    def _parse_note_heading(self, value: str) -> tuple[str | None, str | None]:
        normalized = value.strip()
        normalized = re.sub(r"[\u2013\u2014\u2011\u2212\uFF1F\?]+", "-", normalized)
        normalized = normalized.replace("\uFF1A", ":")
        normalized = normalized.replace("\uFFFD", "-")
        normalized = re.sub(r"\s+", " ", normalized)

        match = re.search(r"\b(note\s+\d+[a-z]?)\b(?:\s*[-:]\s*|\s+)(.+)$", normalized, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().title(), match.group(2).strip()

        fallback = re.search(r"\b(note\s+\d+[a-z]?)\b", normalized, flags=re.IGNORECASE)
        if fallback:
            return fallback.group(1).strip().title(), None
        return None, None

    def _is_generic_notes_title(self, value: str | None) -> bool:
        if not value:
            return True
        normalized = self._normalize_text(value)
        return normalized in {
            "",
            "notes to consolidated financial statements",
            "notes to financial statements",
        }

    def _looks_like_primary_statement(self, table: ParsedTable) -> bool:
        title = self._normalize_text(table.title or "")
        patterns = self._PRIMARY_STATEMENT_PATTERNS.get(table.table_type or "", ())
        return any(pattern in title for pattern in patterns)

    def _normalize_text(self, value: str) -> str:
        normalized = value.lower().replace("\u2019", "'").replace("\u2018", "'")
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()
