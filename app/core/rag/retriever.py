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
            fallback_segments = self._segment_repository.list_for_document(doc_id)[:top_k]
            return [(segment, 0.01) for segment in fallback_segments]

        candidates = self._build_candidates(
            merged,
            question=question,
            section_hints=section_hints,
            metric_keys=metric_keys,
        )
        candidates = self._filter_evidence_free_references(candidates)
        candidates = self._deduplicate_candidates(candidates)
        reranked = self._reranker.rerank(question, candidates, keep_top_k=top_k)
        if reranked:
            return reranked
        return candidates[:top_k]

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
    ) -> list[tuple[DocumentSegment, float]]:
        hints = set(section_hints or [])
        metrics = set(metric_keys or [])
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
            )
            candidates.append((segment, combined_score))

        candidates.sort(
            key=lambda item: (item[1], len(item[0].content)),
            reverse=True,
        )
        return candidates

    @staticmethod
    def _query_aware_adjustment(
        segment: DocumentSegment,
        *,
        question_fold: str,
        section_hints: set[str],
        metric_keys: set[str],
    ) -> float:
        """Boost owned sections; penalize common hard-negative families before rerank."""
        metadata = segment.metadata or {}
        section_type = str(metadata.get("section_type") or "")
        content = segment.content.casefold()
        delta = 0.0

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

        risk_q = "risk_section" in section_hints or "风险" in question_fold or "risk" in question_fold
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
