from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api import dependencies  # noqa: E402
from app.core.errors import DocumentNotFoundError  # noqa: E402
from app.core.kg import KnowledgeGraphBuilder  # noqa: E402
from src.claude_copilot.schemas.document import DocumentProcessingStatus  # noqa: E402


@dataclass
class BackfillStats:
    processed_docs: int = 0
    skipped_docs: int = 0
    failed_docs: int = 0
    total_nodes: int = 0
    total_relationships: int = 0


def main() -> int:
    document_repository = dependencies.get_document_repository()
    parsed_document_repository = dependencies.get_parsed_document_repository()
    graph_store = dependencies.get_graph_store()
    builder = KnowledgeGraphBuilder()
    stats = BackfillStats()

    for record in document_repository.list():
        if record.status != DocumentProcessingStatus.COMPLETED:
            stats.skipped_docs += 1
            print(f"SKIP {record.doc_id} status={record.status}")
            continue
        try:
            parsed_document = parsed_document_repository.get(record.doc_id)
            graph = builder.build(parsed_document)
            graph_store.replace_document(graph)
            stats.processed_docs += 1
            stats.total_nodes += len(graph.nodes)
            stats.total_relationships += len(graph.relationships)
            print(
                f"OK   {record.doc_id} nodes={len(graph.nodes)} "
                f"relationships={len(graph.relationships)}"
            )
        except DocumentNotFoundError:
            stats.skipped_docs += 1
            print(f"SKIP {record.doc_id} no_parsed_document")
        except Exception as exc:  # pragma: no cover - environment dependent
            stats.failed_docs += 1
            print(f"FAIL {record.doc_id} error={exc}")

    print(
        "SUMMARY "
        f"processed_docs={stats.processed_docs} "
        f"skipped_docs={stats.skipped_docs} "
        f"failed_docs={stats.failed_docs} "
        f"total_nodes={stats.total_nodes} "
        f"total_relationships={stats.total_relationships}"
    )
    return 0 if stats.failed_docs == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
