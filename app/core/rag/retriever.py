import re

from app.core.db import SegmentRepositoryProtocol
from app.core.rag.query_expansion import QueryExpansionService
from app.core.rag.reranking import (
    DeterministicRerankingService,
    RerankingServiceProtocol,
)
from app.core.rag.vector_store import VectorStoreProtocol
from src.claude_copilot.schemas.document import DocumentSegment

_SECTION_BOOST = 0.15
_SECTION_MISMATCH_PENALTY = 0.12
_METRIC_MISMATCH_PENALTY = 0.16
_HR_NOISE_PENALTY = 0.14
_NOTE_TABLE_PENALTY = 0.12
_YEAR_MATCH_BOOST = 0.08
_RELATIVE_SCORE_FLOOR = 0.35
_WINDOW_SCORE_DECAY = 0.85
_COMPANY_IDENTITY_BOOST = 0.08
_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")

_REVENUE_CUES = ("营业收入", "营收", "revenue", "主营业务收入")
_OCF_CUES = (
    "经营活动产生的现金流量净额",
    "经营活动现金流量净额",
    "经营现金流",
    "operating cash flow",
    "cash from operating",
)
_HR_CUES = ("员工培训", "人才梯队", "薪酬", "人力资源", "招聘", "岗位学习")
_NOTE_TABLE_CUES = ("金融资产", "金融负债", "合同负债", "公允价值", "fair value", "level 3")


def _coerce_years(value: object) -> set[int]:
    years: set[int] = set()
    if isinstance(value, bool):
        return years
    if isinstance(value, int) and 1900 <= value <= 2100:
        years.add(value)
    elif isinstance(value, str):
        years.update(int(match) for match in _YEAR_RE.findall(value))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            years.update(_coerce_years(item))
    return years


def segment_period_years(segment: DocumentSegment) -> set[int]:
    """Fact-level years from metadata and text; ignore document-level `year`."""
    years: set[int] = set()
    metadata = segment.metadata or {}
    years.update(_coerce_years(metadata.get("period_year")))
    years.update(_coerce_years(metadata.get("period_years")))
    years.update(_coerce_years(metadata.get("years")))
    years.update(_coerce_years(metadata.get("period")))
    years.update(_coerce_years(segment.content))
    return years


def segment_matches_requested_years(
    segment: DocumentSegment,
    requested: list[int] | set[int] | None,
) -> bool:
    if not requested:
        return True
    found = segment_period_years(segment)
    if not found:
        return True
    return bool(found & set(requested))


def segment_section_type(segment: DocumentSegment) -> str:
    return str((segment.metadata or {}).get("section_type") or "")


def segment_matches_section_hints(
    segment: DocumentSegment,
    hints: list[str] | set[str] | None,
) -> bool:
    if not hints:
        return True
    section_type = segment_section_type(segment)
    return bool(section_type) and section_type in set(hints)


class LocalRetriever:
    def __init__(
        self,
        segment_repository: SegmentRepositoryProtocol,
        vector_store: VectorStoreProtocol | None = None,
        query_expansion: QueryExpansionService | None = None,
        reranker: RerankingServiceProtocol | None = None,
        candidate_multiplier: int = 4,
        vector_weight: float = 0.65,
        lexical_weight: float = 0.35,
    ) -> None:
        self._segment_repository = segment_repository
        self._vector_store = vector_store
        self._query_expansion = query_expansion or QueryExpansionService()
        self._reranker = reranker or DeterministicRerankingService()
        self._candidate_multiplier = max(1, candidate_multiplier)
        self._vector_weight = vector_weight
        self._lexical_weight = lexical_weight

    def retrieve(
        self,
        question: str,
        *,
        doc_id: str,
        top_k: int = 3,
        section_hints: list[str] | None = None,
        metric_keys: list[str] | None = None,
        years: list[int] | None = None,
    ) -> list[tuple[DocumentSegment, float]]:
        merged: dict[str, dict[str, object]] = {}
        candidate_k = max(top_k, top_k * self._candidate_multiplier)

        for query in self._query_expansion.expand(question):
            vector_hits: list[tuple[DocumentSegment, float]] = []
            if self._vector_store is not None:
                vector_hits = self._vector_store.search(query, doc_id=doc_id, top_k=candidate_k)
            for segment, score in vector_hits:
                self._merge_hit(
                    merged,
                    segment=segment,
                    vector_score=score,
                    lexical_score=0.0,
                )

            lexical_hits = self._segment_repository.search(query, doc_id=doc_id, top_k=candidate_k)
            for segment, score in lexical_hits:
                self._merge_hit(
                    merged,
                    segment=segment,
                    vector_score=0.0,
                    lexical_score=score,
                )

        if not merged:
            fallback_segments = self._segment_repository.list_for_document(doc_id)
            fallback = [(segment, 0.01) for segment in fallback_segments]
            fallback = self._apply_section_constraint(fallback, section_hints)
            fallback = self._apply_year_constraint(fallback, years)
            return self._attach_retrieval_diagnostics(fallback[:top_k], merged)

        candidates = self._build_candidates(
            merged,
            question=question,
            section_hints=section_hints,
            metric_keys=metric_keys,
            years=years,
        )
        candidates = self._apply_section_constraint(candidates, section_hints)
        candidates = self._apply_year_constraint(candidates, years)
        candidates = self._apply_score_floor(candidates)
        candidates = self._expand_position_windows(
            candidates,
            doc_id=doc_id,
            years=years,
            section_hints=section_hints,
            seed_k=max(top_k, 3),
        )
        candidates = self._filter_evidence_free_references(candidates)
        candidates = self._deduplicate_candidates(candidates)
        fused_scores = {
            segment.segment_id: score for segment, score in candidates
        }
        reranked = self._reranker.rerank(question, candidates, keep_top_k=top_k)
        rerank_scores = {
            segment.segment_id: score for segment, score in reranked
        }
        final = self._apply_post_rerank_adjustments(
            reranked if reranked else candidates[:top_k],
            question=question,
        )
        return self._attach_retrieval_diagnostics(
            final,
            merged,
            fused_scores=fused_scores,
            rerank_scores=rerank_scores,
        )

    @staticmethod
    def _apply_post_rerank_adjustments(
        hits: list[tuple[DocumentSegment, float]],
        *,
        question: str,
    ) -> list[tuple[DocumentSegment, float]]:
        """Use layout evidence for narrow intents that semantic rerankers miss."""
        normalized = question.casefold()
        identity_query = any(
            cue in normalized
            for cue in ("公司全称", "公司名称", "企业全称", "full company name", "legal name")
        )
        if not identity_query:
            return hits

        adjusted: list[tuple[DocumentSegment, float]] = []
        for segment, score in hits:
            metadata = segment.metadata or {}
            compact = re.sub(r"\s+", "", segment.content)
            legal_name = any(
                suffix in compact.casefold()
                for suffix in (
                    "股份有限公司",
                    "有限责任公司",
                    "有限公司",
                    " corporation",
                    " company limited",
                    " inc.",
                    " ltd.",
                )
            )
            cover_heading = (
                metadata.get("block_type") == "heading"
                and metadata.get("page") in {0, 1}
                and len(compact) <= 80
            )
            bonus = _COMPANY_IDENTITY_BOOST if legal_name and cover_heading else 0.0
            adjusted.append((segment, score + bonus))
        return sorted(adjusted, key=lambda item: item[1], reverse=True)

    def _merge_hit(
        self,
        merged: dict[str, dict[str, object]],
        *,
        segment: DocumentSegment,
        vector_score: float,
        lexical_score: float,
    ) -> None:
        bucket = merged.setdefault(
            segment.segment_id,
            {
                "segment": segment,
                "vector_score": 0.0,
                "lexical_score": 0.0,
            },
        )
        bucket["segment"] = segment
        bucket["vector_score"] = max(float(bucket["vector_score"]), vector_score)
        bucket["lexical_score"] = max(float(bucket["lexical_score"]), lexical_score)

    def _build_candidates(
        self,
        merged: dict[str, dict[str, object]],
        *,
        question: str,
        section_hints: list[str] | None = None,
        metric_keys: list[str] | None = None,
        years: list[int] | None = None,
    ) -> list[tuple[DocumentSegment, float]]:
        hints = set(section_hints or [])
        metrics = set(metric_keys or [])
        requested_years = set(years or [])
        question_fold = question.casefold()
        candidates: list[tuple[DocumentSegment, float]] = []
        for item in merged.values():
            segment = item["segment"]
            vector_score = float(item["vector_score"])
            lexical_score = float(item["lexical_score"])
            combined_score = (
                vector_score * self._vector_weight
                + lexical_score * self._lexical_weight
            )
            combined_score += self._query_aware_adjustment(
                segment,
                question_fold=question_fold,
                section_hints=hints,
                metric_keys=metrics,
                years=requested_years,
            )
            candidates.append((segment, combined_score))

        candidates.sort(
            key=lambda item: (item[1], len(item[0].content)),
            reverse=True,
        )
        return candidates

    @staticmethod
    def _apply_year_constraint(
        candidates: list[tuple[DocumentSegment, float]],
        years: list[int] | None,
    ) -> list[tuple[DocumentSegment, float]]:
        if not years:
            return candidates
        matched = [
            item
            for item in candidates
            if segment_matches_requested_years(item[0], years)
        ]
        return matched if matched else candidates

    @staticmethod
    def _apply_section_constraint(
        candidates: list[tuple[DocumentSegment, float]],
        section_hints: list[str] | None,
    ) -> list[tuple[DocumentSegment, float]]:
        if not section_hints:
            return candidates
        matched = [
            item
            for item in candidates
            if segment_matches_section_hints(item[0], section_hints)
        ]
        return matched if matched else candidates

    @staticmethod
    def _apply_score_floor(
        candidates: list[tuple[DocumentSegment, float]],
        *,
        relative_floor: float = _RELATIVE_SCORE_FLOOR,
    ) -> list[tuple[DocumentSegment, float]]:
        """Drop fused hits far below the best score (RAGFlow similarity threshold)."""
        if len(candidates) <= 1:
            return candidates
        best = max(score for _, score in candidates)
        if best <= 0:
            return candidates
        kept = [
            item for item in candidates if item[1] >= best * relative_floor
        ]
        return kept if kept else candidates[:1]

    def _expand_position_windows(
        self,
        candidates: list[tuple[DocumentSegment, float]],
        *,
        doc_id: str,
        years: list[int] | None,
        section_hints: list[str] | None,
        seed_k: int,
    ) -> list[tuple[DocumentSegment, float]]:
        """Pull same-section ±1 neighbors so table headers stay with values."""
        if not candidates:
            return candidates
        siblings = self._segment_repository.list_for_document(doc_id)
        by_position = {segment.position: segment for segment in siblings}
        expanded = list(candidates)
        seen = {segment.segment_id for segment, _ in candidates}
        for segment, score in candidates[: max(1, seed_k)]:
            source_section = segment_section_type(segment)
            for neighbor_pos in (segment.position - 1, segment.position + 1):
                neighbor = by_position.get(neighbor_pos)
                if neighbor is None or neighbor.segment_id in seen:
                    continue
                neighbor_section = segment_section_type(neighbor)
                if (
                    source_section
                    and neighbor_section
                    and source_section != neighbor_section
                ):
                    continue
                if not segment_matches_requested_years(neighbor, years):
                    continue
                if neighbor_section and not segment_matches_section_hints(
                    neighbor, section_hints
                ):
                    continue
                seen.add(neighbor.segment_id)
                expanded.append((neighbor, score * _WINDOW_SCORE_DECAY))
        expanded.sort(key=lambda item: (item[1], len(item[0].content)), reverse=True)
        return expanded

    @staticmethod
    def _attach_retrieval_diagnostics(
        hits: list[tuple[DocumentSegment, float]],
        merged: dict[str, dict[str, object]],
        *,
        fused_scores: dict[str, float] | None = None,
        rerank_scores: dict[str, float] | None = None,
    ) -> list[tuple[DocumentSegment, float]]:
        annotated: list[tuple[DocumentSegment, float]] = []
        for segment, score in hits:
            bucket = merged.get(segment.segment_id) or {}
            metadata = dict(segment.metadata or {})
            page = metadata.get("page")
            if page is None:
                page = metadata.get("page_start")
            page_range = metadata.get("page_range")
            if page is None and isinstance(page_range, (list, tuple)) and page_range:
                page = page_range[0]
            metadata["retrieval"] = {
                "vector_score": round(float(bucket.get("vector_score") or 0.0), 4),
                "lexical_score": round(float(bucket.get("lexical_score") or 0.0), 4),
                "fused_score": round(
                    float((fused_scores or {}).get(segment.segment_id, score)),
                    4,
                ),
                "rerank_score": round(
                    float((rerank_scores or {}).get(segment.segment_id, score)),
                    4,
                ),
                "final_score": round(float(score), 4),
                "position": segment.position,
                "page": page,
            }
            annotated.append(
                (segment.model_copy(update={"metadata": metadata}), score)
            )
        return annotated

    @staticmethod
    def _query_aware_adjustment(
        segment: DocumentSegment,
        *,
        question_fold: str,
        section_hints: set[str],
        metric_keys: set[str],
        years: set[int] | None = None,
    ) -> float:
        """Boost owned sections; penalize common hard-negative families before rerank."""
        metadata = segment.metadata or {}
        section_type = str(metadata.get("section_type") or "")
        content = segment.content.casefold()
        delta = 0.0
        requested_years = years or set()
        if requested_years and segment_period_years(segment) & requested_years:
            delta += _YEAR_MATCH_BOOST

        if section_hints:
            if section_type in section_hints:
                delta += _SECTION_BOOST
            elif section_type:
                # Risk/MD&A ownership: demote statement/note/audit when they are not hinted.
                if "risk_section" in section_hints and section_type in {
                    "financial_statement",
                    "financial_note",
                }:
                    delta -= _SECTION_MISMATCH_PENALTY
                if "management_discussion" in section_hints and section_type in {
                    "audit_report",
                    "financial_note",
                    "company_overview",
                }:
                    delta -= _SECTION_MISMATCH_PENALTY * 0.75

        wants_ocf = (
            "net_cash_from_operating_activities" in metric_keys
            or any(cue in question_fold for cue in _OCF_CUES)
        )
        wants_revenue = "revenue" in metric_keys or any(
            cue in question_fold for cue in ("营业收入", "营收", "revenue")
        )
        if wants_ocf and not wants_revenue:
            has_ocf = any(cue in content for cue in _OCF_CUES)
            has_revenue = any(cue in content for cue in _REVENUE_CUES)
            if has_revenue and not has_ocf:
                delta -= _METRIC_MISMATCH_PENALTY
        if wants_revenue and not wants_ocf:
            has_ocf = any(cue in content for cue in _OCF_CUES)
            has_revenue = any(cue in content for cue in _REVENUE_CUES)
            if has_ocf and not has_revenue:
                delta -= _METRIC_MISMATCH_PENALTY

        business_driver_q = any(
            cue in question_fold for cue in ("驱动", "增长", "经营情况", "主营业务", "driver")
        )
        if business_driver_q and any(cue in content for cue in _HR_CUES):
            if not any(cue in content for cue in ("营业收入", "营收", "revenue", "毛利")):
                delta -= _HR_NOISE_PENALTY

        risk_q = (
            "risk_section" in section_hints
            or "风险" in question_fold
            or "risk" in question_fold
        )
        if risk_q and any(cue in content for cue in _NOTE_TABLE_CUES):
            if section_type in {"financial_statement", "financial_note", ""}:
                delta -= _NOTE_TABLE_PENALTY

        return delta

    @staticmethod
    def _filter_evidence_free_references(
        candidates: list[tuple[DocumentSegment, float]],
    ) -> list[tuple[DocumentSegment, float]]:
        """Drop short cross-references that point elsewhere but contain no evidence."""
        kept: list[tuple[DocumentSegment, float]] = []
        for segment, score in candidates:
            compact = re.sub(r"\s+", "", segment.content)
            reference_only = (
                len(compact) <= 80
                and any(
                    marker in compact
                    for marker in ("参见", "详见", "请见", "见本报告", "本报告")
                )
                and any(marker in compact for marker in ("第", "章节", "部分", "中", "之"))
                and re.search(r"\d+(?:\.\d+)?%", compact) is None
            )
            if reference_only:
                continue
            kept.append((segment, score))
        return kept

    @staticmethod
    def _deduplicate_candidates(
        candidates: list[tuple[DocumentSegment, float]],
    ) -> list[tuple[DocumentSegment, float]]:
        """Keep the highest-scored copy of text duplicated by parse/chunk boundaries."""
        unique: list[tuple[DocumentSegment, float]] = []
        seen_content: set[str] = set()
        seen_long_content: list[str] = []
        for segment, score in candidates:
            normalized = re.sub(r"\s+", "", segment.content).casefold()
            if normalized and normalized in seen_content:
                continue
            if len(normalized) >= 120 and any(
                normalized in existing or existing in normalized
                for existing in seen_long_content
            ):
                continue
            if normalized:
                seen_content.add(normalized)
            if len(normalized) >= 120:
                seen_long_content.append(normalized)
            unique.append((segment, score))
        return unique
