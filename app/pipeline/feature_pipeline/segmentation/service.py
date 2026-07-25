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
                "管理层讨论与分析",
                "经营情况讨论与分析",
                "董事会报告",
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
                "可能面对的风险",
                "公司可能面对的风险",
                "风险因素",
                "主要风险",
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
                "合并资产负债表",
                "合并利润表",
                "合并现金流量表",
                "合并股东权益变动表",
                "合并所有者权益变动表",
                "母公司资产负债表",
                "母公司利润表",
                "母公司现金流量表",
                "资产负债表",
                "利润表",
                "现金流量表",
                "财务报表",
                "财务报告",
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
                "财务报表附注",
                "财务附注",
                "附注",
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
                "审计报告",
                "审计意见",
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
                "公司简介和主要财务指标",
                "公司简介",
                "主要财务指标",
            ),
            0.9,
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
        candidates: list[SemanticSegmentCandidate] = []
        if document.page_blocks:
            candidates = self._build_candidates_from_page_blocks(document.page_blocks)
        if not candidates:
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
            if self._is_semantic_anchor(block)
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
            title = self._normalize_anchor_text(heading_block.text) or heading_block.text.strip()
            semantic_type, confidence = self._classify_heading(title)
            candidates.append(
                SemanticSegmentCandidate(
                    title=title,
                    blocks=candidate_blocks,
                    semantic_type=semantic_type,
                    confidence=confidence,
                    anchor_block_id=heading_block.block_id,
                )
            )

        return self._merge_adjacent_candidates(candidates)

    def _is_semantic_anchor(self, block: ParsedPageBlock) -> bool:
        text = self._normalize_anchor_text(block.text.strip())
        if not text or len(text) > 60:
            return False
        if block.block_type not in {"heading", "paragraph"}:
            return False
        semantic_type, _confidence = self._classify_heading(text)
        if semantic_type == "generic_section":
            return False
        # Reject mid-sentence mentions such as “详见...管理层讨论与分析...”
        if not self._looks_like_section_title(text, semantic_type):
            return False
        return True

    def _normalize_anchor_text(self, text: str) -> str:
        # TOC lines often prefix a page number: "11第三节管理层讨论与分析"
        cleaned = re.sub(r"^\d{1,3}(?=第)", "", text.strip())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _compact_text(self, text: str) -> str:
        return re.sub(r"\s+", "", text)

    def _looks_like_section_title(self, text: str, semantic_type: str) -> bool:
        normalized = self._normalize_anchor_text(text)
        compact = self._compact_text(normalized)
        if len(compact) > 48:
            return False
        if re.search(r"(详见|请见|参见|如下|下列|所述|之“|之\")", compact):
            return False
        if re.search(r"(治理层|对财务报表的责任)", compact):
            return False
        if normalized.endswith(("。", "；", ";", "，", ",")):
            return False
        numbered = bool(
            re.match(
                r"^(第[一二三四五六七八九十百千零〇\d]+[章节篇部]"
                r"|[（(]?[一二三四五六七八九十]+[、.．)]"
                r"|\d+[、.．]"
                r"|[一二三四五六七八九十]+、)",
                compact,
            )
        )
        if numbered and semantic_type in {
            "management_discussion",
            "company_overview",
            "financial_statement",
            "audit_report",
            "risk_section",
            "financial_note",
        }:
            return True
        # Exact-ish title forms for Chinese/English statement headings.
        if semantic_type in {"financial_statement", "management_discussion", "audit_report", "company_overview", "risk_section"}:
            return bool(
                re.match(
                    r"^(第[一二三四五六七八九十百千零〇\d]+[章节篇部])?"
                    r"(合并|母公司)?(资产负债表|利润表|现金流量表|股东权益变动表|所有者权益变动表)"
                    r"|^(第[一二三四五六七八九十百千零〇\d]+[章节篇部])?"
                    r"(管理层讨论与分析|经营情况讨论与分析|公司简介和主要财务指标|公司简介|审计报告|风险因素)"
                    r"|^(consolidated|notes to|management|risk factors|financial statements)",
                    compact,
                    flags=re.IGNORECASE,
                )
                or re.match(
                    r"^(consolidated|notes to|management|risk factors|financial statements)",
                    normalized,
                    flags=re.IGNORECASE,
                )
            )
        return numbered

    def _build_candidates_from_sections(self, sections: list[ParsedSection]) -> list[SemanticSegmentCandidate]:
        candidates: list[SemanticSegmentCandidate] = []
        for section in sections:
            title = (section.title or "").strip()
            if not title or re.fullmatch(r"Page \d+", title):
                continue
            semantic_type, confidence = self._classify_heading(title)
            if semantic_type == "generic_section":
                continue
            if not self._looks_like_section_title(title, semantic_type) and len(title) > 60:
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
            same_title = candidate.title == previous.title
            same_type = candidate.semantic_type == previous.semantic_type
            previous_pages = [block.page for block in previous.blocks if block.page is not None]
            candidate_pages = [block.page for block in candidate.blocks if block.page is not None]
            page_gap = 999
            if previous_pages and candidate_pages:
                page_gap = min(candidate_pages) - max(previous_pages)

            # Merge same title, or same type across nearby continuation pages.
            if (same_title and same_type) or (same_type and page_gap <= 1 and not self._is_major_section_title(candidate.title)):
                previous.blocks.extend(candidate.blocks)
                previous.confidence = max(previous.confidence, candidate.confidence)
                if len(candidate.title) < len(previous.title) and self._is_major_section_title(candidate.title):
                    previous.title = candidate.title
                continue
            merged.append(candidate)
        return merged

    def _is_major_section_title(self, title: str) -> bool:
        return bool(
            re.match(
                r"^第[一二三四五六七八九十百千零〇\d]+[章节篇部]",
                title.strip(),
            )
            or re.match(
                r"^(合并|母公司)?(资产负债表|利润表|现金流量表)|管理层讨论与分析|审计报告",
                title.strip(),
            )
        )

    def _classify_heading(self, heading: str) -> tuple[str, float]:
        normalized = self._normalize_text(heading)
        compact = self._compact_text(normalized)
        # Prefer longer pattern matches to avoid "附注"/"财务报表" over-matching.
        best: tuple[str, float] | None = None
        best_len = -1
        for semantic_type, patterns, confidence in self._SECTION_PATTERNS:
            for pattern in patterns:
                pattern_norm = pattern.lower()
                pattern_compact = self._compact_text(pattern_norm)
                if pattern_norm not in normalized and pattern_compact not in compact:
                    continue
                score_len = len(pattern_compact)
                if score_len <= best_len:
                    continue
                # Avoid bare "附注"/generic financial-report matches inside narrative.
                if pattern_compact in {"附注", "财务报告", "财务报表", "overview"}:
                    if len(compact) > len(pattern_compact) + 6:
                        continue
                    if re.search(r"(责任|治理层|内部控制)", compact):
                        continue
                if pattern_compact in {"审计报告", "审计意见"}:
                    if "内部控制" in compact:
                        continue
                    # Reject narrative mentions such as “对最近一期非标准审计报告相关情况的说明”.
                    if len(compact) > len(pattern_compact) + 8:
                        continue
                best = (semantic_type, confidence)
                best_len = score_len
        if best is not None:
            return best
        return "generic_section", 0.55

    def _normalize_text(self, text: str) -> str:
        normalized = self._normalize_anchor_text(text).lower()
        normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
        normalized = normalized.replace("&", " and ")
        # Keep Chinese section titles searchable after lowercasing Latin parts.
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
