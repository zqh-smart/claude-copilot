from __future__ import annotations

from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.core.errors import PersistenceBackendError
from app.core.rag.embeddings import EmbeddingServiceProtocol
from src.claude_copilot.schemas.document import DocumentSegment


class VectorStoreProtocol(Protocol):
    def replace_for_document(self, doc_id: str, segments: list[DocumentSegment]) -> None:
        ...

    def search(
        self,
        query: str,
        *,
        doc_id: str | None = None,
        top_k: int = 3,
    ) -> list[tuple[DocumentSegment, float]]:
        ...


class NoOpVectorStore:
    def replace_for_document(self, doc_id: str, segments: list[DocumentSegment]) -> None:
        return None

    def search(
        self,
        query: str,
        *,
        doc_id: str | None = None,
        top_k: int = 3,
    ) -> list[tuple[DocumentSegment, float]]:
        return []


class QdrantVectorStore:
    def __init__(
        self,
        *,
        client: QdrantClient,
        collection_name: str,
        embedding_service: EmbeddingServiceProtocol,
        batch_size: int = 64,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._embedding_service = embedding_service
        self._batch_size = max(1, batch_size)
        self._initialized = False

    def replace_for_document(self, doc_id: str, segments: list[DocumentSegment]) -> None:
        self._ensure_collection()
        self._delete_document(doc_id)

        if not segments:
            return

        for start in range(0, len(segments), self._batch_size):
            batch = segments[start : start + self._batch_size]
            vectors = self._embedding_service.embed_documents(
                [self._content_for_embedding(segment) for segment in batch]
            )
            points = [
                models.PointStruct(
                    id=self._point_id(segment.segment_id),
                    vector=vector,
                    payload=self._segment_payload(segment),
                )
                for segment, vector in zip(batch, vectors, strict=True)
            ]
            self._client.upsert(
                collection_name=self._collection_name,
                points=points,
                wait=True,
            )

    def search(
        self,
        query: str,
        *,
        doc_id: str | None = None,
        top_k: int = 3,
    ) -> list[tuple[DocumentSegment, float]]:
        self._ensure_collection()

        query_filter = None
        if doc_id is not None:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id),
                    )
                ]
            )

        response = self._client.query_points(
            collection_name=self._collection_name,
            query=self._embedding_service.embed_query(query),
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )

        hits: list[tuple[DocumentSegment, float]] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append((self._segment_from_payload(payload), float(point.score or 0.0)))
        return hits

    def _ensure_collection(self) -> None:
        if self._initialized:
            return

        vector_size = self._embedding_service.dimensions
        if not self._client.collection_exists(self._collection_name):
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name="doc_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
        else:
            info = self._client.get_collection(self._collection_name)
            vectors_config = info.config.params.vectors
            existing_size = getattr(vectors_config, "size", None)
            if existing_size != vector_size:
                raise PersistenceBackendError(
                    "Qdrant collection vector size mismatch: "
                    f"collection={existing_size}, embedding_dimensions={vector_size}."
                )

        self._initialized = True

    def _delete_document(self, doc_id: str) -> None:
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id),
                    )
                ]
            ),
            wait=True,
        )

    @staticmethod
    def _point_id(segment_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, segment_id))

    @staticmethod
    def _content_for_embedding(segment: DocumentSegment) -> str:
        return segment.content_summary or segment.content

    @staticmethod
    def _segment_payload(segment: DocumentSegment) -> dict:
        return {
            "segment_id": segment.segment_id,
            "document_id": segment.document_id,
            "doc_id": segment.document_id,
            "parent_section_id": segment.parent_section_id,
            "position": segment.position,
            "content": segment.content,
            "content_summary": segment.content_summary,
            "keywords": list(segment.keywords),
            "metadata": dict(segment.metadata),
        }

    @staticmethod
    def _segment_from_payload(payload: dict) -> DocumentSegment:
        return DocumentSegment.model_validate(
            {
                "segment_id": payload["segment_id"],
                "document_id": payload.get("document_id") or payload.get("doc_id"),
                "parent_section_id": payload.get("parent_section_id"),
                "position": payload["position"],
                "content": payload["content"],
                "content_summary": payload.get("content_summary"),
                "keywords": payload.get("keywords") or [],
                "metadata": payload.get("metadata") or {},
            }
        )
