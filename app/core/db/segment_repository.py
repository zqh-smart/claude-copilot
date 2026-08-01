import json
from pathlib import Path
from threading import RLock

from app.core.db.lexical import bm25_lite_score, tokenize
from src.claude_copilot.schemas.document import DocumentSegment


class LocalSegmentRepository:
    def __init__(self, base_dir: str) -> None:
        self._file_path = Path(base_dir) / "segments_index.json"
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def replace_for_document(self, doc_id: str, segments: list[DocumentSegment]) -> None:
        with self._lock:
            payload = self._read_all()
            payload[doc_id] = [segment.model_dump(mode="json") for segment in segments]
            self._write_all(payload)

    def list_for_document(self, doc_id: str) -> list[DocumentSegment]:
        with self._lock:
            payload = self._read_all()
        return [DocumentSegment.model_validate(item) for item in payload.get(doc_id, [])]

    def search(self, query: str, *, doc_id: str | None = None, top_k: int = 3) -> list[tuple[DocumentSegment, float]]:
        query_tokens = tokenize(query)
        with self._lock:
            payload = self._read_all()
        items = payload.items() if doc_id is None else [(doc_id, payload.get(doc_id, []))]

        scored: list[tuple[DocumentSegment, float]] = []
        for _, segment_items in items:
            if not segment_items:
                continue
            for item in segment_items:
                segment = DocumentSegment.model_validate(item)
                score = bm25_lite_score(query_tokens, segment.content)
                if score > 0:
                    scored.append((segment, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def _read_all(self) -> dict[str, list[dict]]:
        if not self._file_path.exists():
            return {}
        raw = self._file_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        return json.loads(raw)

    def _write_all(self, payload: dict[str, list[dict]]) -> None:
        temporary = self._file_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self._file_path)
