from app.core.db import SegmentRepositoryProtocol
from app.core.rag.query_expansion import QueryExpansionService
from app.core.rag.reranking import (
    DeterministicRerankingService,
    RerankingServiceProtocol,
)
from app.core.rag.vector_store import VectorStoreProtocol
from src.claude_copilot.schemas.document import DocumentSegment

_SECTION_BOOST = 0.15


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

        candidates = self._build_candidates(merged, section_hints=section_hints)
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
        section_hints: list[str] | None = None,
    ) -> list[tuple[DocumentSegment, float]]:
        hints = set(section_hints or [])
        candidates: list[tuple[DocumentSegment, float]] = []
        for item in merged.values():
            segment = item["segment"]
            vector_score = float(item["vector_score"])
            lexical_score = float(item["lexical_score"])
            combined_score = (
                vector_score * self._vector_weight
                + lexical_score * self._lexical_weight
            )
            if hints:
                section_type = (segment.metadata or {}).get("section_type")
                if section_type in hints:
                    combined_score += _SECTION_BOOST
            candidates.append((segment, combined_score))

        candidates.sort(
            key=lambda item: (item[1], len(item[0].content)),
            reverse=True,
        )
        return candidates
