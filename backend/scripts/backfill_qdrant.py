from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api import dependencies
from app.core.errors import DocumentNotFoundError
from src.claude_copilot.schemas.document import DocumentProcessingStatus


@dataclass
class BackfillStats:
    processed_docs: int = 0
    skipped_docs: int = 0
    failed_docs: int = 0
    total_segments: int = 0


def main() -> int:
    document_repository = dependencies.get_document_repository()
    parsed_document_repository = dependencies.get_parsed_document_repository()
    segment_repository = dependencies.get_segment_repository()
    vector_store = dependencies.get_vector_store()

    stats = BackfillStats()
    documents = document_repository.list()

    for record in documents:
        if record.status != DocumentProcessingStatus.COMPLETED:
            stats.skipped_docs += 1
            print(f"SKIP {record.doc_id} status={record.status}")
            continue

        try:
            parsed_document = parsed_document_repository.get(record.doc_id)
            segments = parsed_document.segments
        except DocumentNotFoundError:
            segments = []

        if not segments:
            segments = segment_repository.list_for_document(record.doc_id)

        if not segments:
            stats.skipped_docs += 1
            print(f"SKIP {record.doc_id} no_segments")
            continue

        try:
            vector_store.replace_for_document(record.doc_id, segments)
            stats.processed_docs += 1
            stats.total_segments += len(segments)
            print(f"OK   {record.doc_id} segments={len(segments)}")
        except Exception as exc:  # pragma: no cover - environment dependent
            stats.failed_docs += 1
            print(f"FAIL {record.doc_id} error={exc}")

    print(
        "SUMMARY "
        f"processed_docs={stats.processed_docs} "
        f"skipped_docs={stats.skipped_docs} "
        f"failed_docs={stats.failed_docs} "
        f"total_segments={stats.total_segments}"
    )
    return 0 if stats.failed_docs == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
