from app.core.db import SegmentRepositoryProtocol
from app.core.rag.vector_store import VectorStoreProtocol
from src.claude_copilot.schemas.document import DocumentSegment


class IndexingService:
    """Dify-style segment persistence with a local repository backend."""

    def __init__(
        self,
        segment_repository: SegmentRepositoryProtocol,
        vector_store: VectorStoreProtocol | None = None,
    ) -> None:
        self._segment_repository = segment_repository
        self._vector_store = vector_store

    def index(self, doc_id: str, segments: list[DocumentSegment]) -> int:
        self._segment_repository.replace_for_document(doc_id, segments)
        if self._vector_store is not None:
            self._vector_store.replace_for_document(doc_id, segments)
        return len(segments)
