from __future__ import annotations

from typing import Protocol

import httpx

from app.core.config import Settings
from src.claude_copilot.schemas.document import DocumentSegment


class RerankingServiceProtocol(Protocol):
    def rerank(
        self,
        query: str,
        hits: list[tuple[DocumentSegment, float]],
        *,
        keep_top_k: int = 3,
    ) -> list[tuple[DocumentSegment, float]]:
        ...


class DeterministicRerankingService:
    def rerank(
        self,
        query: str,
        hits: list[tuple[DocumentSegment, float]],
        *,
        keep_top_k: int = 3,
    ) -> list[tuple[DocumentSegment, float]]:
        ranked = sorted(
            hits,
            key=lambda item: (item[1], len(item[0].content)),
            reverse=True,
        )
        return ranked[:keep_top_k]


class SiliconRerankingService:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        self._model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def rerank(
        self,
        query: str,
        hits: list[tuple[DocumentSegment, float]],
        *,
        keep_top_k: int = 3,
    ) -> list[tuple[DocumentSegment, float]]:
        if not hits:
            return []

        passages = [segment.content for segment, _ in hits]
        payload = {
            "model": self._model,
            "query": query,
            "documents": passages,
            "top_n": min(keep_top_k, len(passages)),
            "return_documents": False,
            "max_chunks_per_doc": 1024,
            "overlap_tokens": 80,
        }
        response = self._client.post("/rerank", json=payload)
        response.raise_for_status()
        results = response.json().get("results", [])

        reranked: list[tuple[DocumentSegment, float]] = []
        for item in results:
            index = int(item["index"])
            segment, original_score = hits[index]
            rerank_score = float(item.get("relevance_score", original_score))
            reranked.append((segment, rerank_score))
        return reranked


def build_reranking_service(settings: Settings) -> RerankingServiceProtocol:
    backend = settings.rerank_backend

    if backend == "silicon" and settings.silicon_key:
        return SiliconRerankingService(
            api_key=settings.silicon_key,
            base_url=settings.silicon_base_url,
            model=settings.rerank_model_id,
        )

    if backend == "auto" and settings.silicon_key:
        return SiliconRerankingService(
            api_key=settings.silicon_key,
            base_url=settings.silicon_base_url,
            model=settings.rerank_model_id,
        )

    return DeterministicRerankingService()
