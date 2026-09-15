from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.core.db import (
    LocalDocumentRepository,
    LocalParsedDocumentRepository,
    LocalSegmentRepository,
    PostgresDocumentRepository,
    PostgresParsedDocumentRepository,
    PostgresSegmentRepository,
    get_postgres_session_factory,
)


def main() -> None:
    settings = get_settings()
    session_factory = get_postgres_session_factory()

    local_document_repository = LocalDocumentRepository(settings.parsed_data_path)
    local_segment_repository = LocalSegmentRepository(settings.parsed_data_path)
    local_parsed_document_repository = LocalParsedDocumentRepository(settings.parsed_data_path)

    postgres_document_repository = PostgresDocumentRepository(session_factory)
    postgres_segment_repository = PostgresSegmentRepository(session_factory)
    postgres_parsed_document_repository = PostgresParsedDocumentRepository(session_factory)

    success_count = 0
    failure_count = 0
    failures: list[dict[str, str]] = []

    for record in local_document_repository.list():
        try:
            postgres_document_repository.save(record)
            segments = local_segment_repository.list_for_document(record.doc_id)
            postgres_segment_repository.replace_for_document(record.doc_id, segments)

            try:
                parsed_document = local_parsed_document_repository.get(record.doc_id)
            except Exception:
                parsed_document = None
            if parsed_document is not None:
                postgres_parsed_document_repository.save(parsed_document)

            success_count += 1
        except Exception as exc:  # pragma: no cover - environment-dependent
            failure_count += 1
            failures.append({"doc_id": record.doc_id, "error": str(exc)})

    summary = {
        "success_count": success_count,
        "failure_count": failure_count,
        "failures": failures,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
