import json
from datetime import datetime
from pathlib import Path

from app.core.errors import DocumentNotFoundError
from src.claude_copilot.schemas.document import DocumentProcessingStatus, DocumentRecord


class LocalDocumentRepository:
    def __init__(self, base_dir: str) -> None:
        self._file_path = Path(base_dir) / "documents_state.json"
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[DocumentRecord]:
        payload = self._read_all()
        return [DocumentRecord.model_validate(item) for item in payload.values()]

    def get(self, doc_id: str) -> DocumentRecord:
        payload = self._read_all()
        item = payload.get(doc_id)
        if item is None:
            raise DocumentNotFoundError(f"Document not found: {doc_id}")
        return DocumentRecord.model_validate(item)

    def save(self, record: DocumentRecord) -> DocumentRecord:
        payload = self._read_all()
        payload[record.doc_id] = record.model_dump(mode="json")
        self._write_all(payload)
        return record

    def update_status(
        self,
        doc_id: str,
        status: DocumentProcessingStatus,
        *,
        parsed_path: str | None = None,
        segment_count: int | None = None,
        error_message: str | None = None,
    ) -> DocumentRecord:
        record = self.get(doc_id)
        record.status = status
        record.updated_at = datetime.utcnow()
        if parsed_path is not None:
            record.parsed_path = parsed_path
        if segment_count is not None:
            record.segment_count = segment_count
        record.error_message = error_message
        return self.save(record)

    def _read_all(self) -> dict[str, dict]:
        if not self._file_path.exists():
            return {}
        raw = self._file_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        return json.loads(raw)

    def _write_all(self, payload: dict[str, dict]) -> None:
        self._file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
