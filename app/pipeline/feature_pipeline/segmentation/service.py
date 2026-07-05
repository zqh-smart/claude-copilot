from __future__ import annotations

import re
from dataclasses import dataclass

from src.claude_copilot.schemas.document import ParsedDocument, ParsedPageBlock, ParsedSection


@dataclass(slots=True)
class SemanticSegmentCandidate:
    title: str
    blocks: list[ParsedPageBlock]
    semantic_type: str
    confidence: float
    anchor_block_id: str | None


class SemanticSegmentationService:
    _SECTION_PATTERNS: list[tuple[str, tuple[str, ...], float]] = [
        (
            "management_discussion",
            (
                "management discussion",
                "management's discussion",
                "management’s discussion",
                "discussion and analysis",
                "md&a",
            ),
            0.96,
        ),
        (
            "risk_section",
            (
                "risk factors",
                "risk factor",
                "risk management",
                "risk overview",
                "credit risk",
                "market risk",
                "liquidity risk",
                "operational risk",
            ),
            0.95,
        ),
        (
            "financial_statement",
            (
                "consolidated balance sheets",
                "consolidated statements of income",
                "consolidated statements of comprehensive income",
                "consolidated statements of cash flows",
                "consolidated statements of changes in stockholders",
                "financial statements",
                "balance sheets",
                "balance sheet",
                "income statement",
                "statements of income",
                "statement of income",
                "cash flow statement",
                "cash flows",
                "statement of cash flows",
            ),
            0.98,
        ),
        (
            "financial_note",
            (
                "notes to consolidated financial statements",
                "notes to financial statements",
                "note 1",
                "note 2",
                "note 3",
                "note 4",
                "note 5",
                "note 6",
                "note 7",
                "note 8",
                "note 9",
            ),
            0.94,
        ),
        (
            "audit_report",
            (
                "report of independent registered public accounting firm",
                "independent auditor",
                "basis for opinions",
                "opinions on the financial statements",
            ),
            0.94,
        ),
        (
            "company_overview",
            (
                "overview",
                "company overview",
                "business overview",
                "about us",
            ),
            0.78,
        ),
    ]

    def segment(self, document: ParsedDocument) -> ParsedDocument:
        semantic_sections = self._build_semantic_sections(document)
        if not semantic_sections:
            return document

        existing_sections = list(document.sections)
        document.sections = existing_sections + semantic_sections
        return document

    def _build_semantic_sections(self, document: ParsedDocument) -> list[ParsedSection]:
        if document.page_blocks:
            candidates = self._build_candidates_from_page_blocks(document.page_blocks)
        else:
            candidates = self._build_candidates_from_sections(document.sections)

        sections: list[ParsedSection] = []
        for index, candidate in enumerate(candidates, start=1):
            content = self._build_candidate_content(candidate)
            if not content.strip():
                continue

            pages = [block.page for block in candidate.blocks if block.page is not None]
            page_start = min(pages) if pages else None
            page_end = max(pages) if pages else None
            section_id = f"{document.doc_id}-semantic-section-{index}"

            sections.append(
                ParsedSection(
                    section_id=section_id,
                    title=candidate.title,
                    content=content,
                    section_type=candidate.semantic_type,
                    page_start=page_start,
                    page_end=page_end,
                    metadata={
                        "source": "semantic_segmentation",
                        "semantic_type": candidate.semantic_type,
                        "confidence": candidate.confidence,
                        "block_count": len(candidate.blocks),
                        "anchor_block_id": candidate.anchor_block_id,
                    },
                )
            )

        return sections

    def _build_candidates_from_page_blocks(self, page_blocks: list[ParsedPageBlock]) -> list[SemanticSegmentCandidate]:
        ordered_blocks = sorted(page_blocks, key=lambda block: (block.page or 0, block.order or 0))
        heading_indices = [
            index
            for index, block in enumerate(ordered_blocks)
            if block.block_type == "heading" and self._classify_heading(block.text)[0] != "generic_section"
        ]
        if not heading_indices:
            return []

        candidates: list[SemanticSegmentCandidate] = []
        for position, heading_index in enumerate(heading_indices):
            heading_block = ordered_blocks[heading_index]
            end_index = heading_indices[position + 1] if position + 1 < len(heading_indices) else len(ordered_blocks)
            candidate_blocks = [
                block
                for block in ordered_blocks[heading_index:end_index]
                if block.block_type not in {"header", "footer"}
            ]
            semantic_type, confidence = self._classify_heading(heading_block.text)
            candidates.append(
                SemanticSegmentCandidate(
                    title=heading_block.text.strip(),
                    blocks=candidate_blocks,
                    semantic_type=semantic_type,
                    confidence=confidence,
                    anchor_block_id=heading_block.block_id,
                )
            )

        return self._merge_adjacent_candidates(candidates)

    def _build_candidates_from_sections(self, sections: list[ParsedSection]) -> list[SemanticSegmentCandidate]:
        candidates: list[SemanticSegmentCandidate] = []
        for section in sections:
            title = (section.title or "").strip()
            if not title or re.fullmatch(r"Page \d+", title):
                continue
            semantic_type, confidence = self._classify_heading(title)
            if semantic_type == "generic_section":
                continue
            block = ParsedPageBlock(
                block_id=section.section_id,
                block_type="heading",
                text=section.content,
                page=section.page_start,
                order=1,
            )
            candidates.append(
                SemanticSegmentCandidate(
                    title=title,
                    blocks=[block],
                    semantic_type=semantic_type,
                    confidence=confidence,
                    anchor_block_id=section.section_id,
                )
            )
        return candidates

    def _merge_adjacent_candidates(
        self,
        candidates: list[SemanticSegmentCandidate],
    ) -> list[SemanticSegmentCandidate]:
        if not candidates:
            return []

        merged: list[SemanticSegmentCandidate] = [candidates[0]]
        for candidate in candidates[1:]:
            previous = merged[-1]
            if candidate.title == previous.title and candidate.semantic_type == previous.semantic_type:
                previous.blocks.extend(candidate.blocks)
                previous.confidence = max(previous.confidence, candidate.confidence)
                continue
            merged.append(candidate)
        return merged

    def _classify_heading(self, heading: str) -> tuple[str, float]:
        normalized = self._normalize_text(heading)
        for semantic_type, patterns, confidence in self._SECTION_PATTERNS:
            if any(pattern in normalized for pattern in patterns):
                return semantic_type, confidence
        return "generic_section", 0.55

    def _normalize_text(self, text: str) -> str:
        normalized = text.lower()
        normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
        normalized = normalized.replace("&", " and ")
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _build_candidate_content(self, candidate: SemanticSegmentCandidate) -> str:
        seen: set[tuple[int | None, int | None, str]] = set()
        parts: list[str] = []

        for block in candidate.blocks:
            text = block.text.strip()
            if not text:
                continue
            dedupe_key = (block.page, block.order, text)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            parts.append(text)

        return "\n\n".join(parts).strip()
