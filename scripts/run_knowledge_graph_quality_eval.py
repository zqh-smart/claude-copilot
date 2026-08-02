"""Evaluate builder quality and configured graph-backend round-trip parity."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api import dependencies  # noqa: E402
from app.core.kg import KnowledgeGraphBuilder, evaluate_document_graph  # noqa: E402
from src.claude_copilot.schemas.document import DocumentProcessingStatus  # noqa: E402

OUT_PATH = ROOT / "data" / "reports" / "kg" / "latest_quality_eval.json"


def main() -> int:
    documents = dependencies.get_document_repository()
    parsed_documents = dependencies.get_parsed_document_repository()
    graph_store = dependencies.get_graph_store()
    builder = KnowledgeGraphBuilder()
    cases: list[dict[str, object]] = []

    for record in documents.list():
        if record.status != DocumentProcessingStatus.COMPLETED:
            continue
        try:
            parsed = parsed_documents.get(record.doc_id)
        except Exception as exc:  # noqa: BLE001
            cases.append(
                {
                    "doc_id": record.doc_id,
                    "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        graph = builder.build(parsed)
        quality = evaluate_document_graph(graph)
        restored = graph_store.get_document(record.doc_id)
        expected_relationship_ids = {item.relationship_id for item in graph.relationships}
        restored_relationship_ids = {item.relationship_id for item in restored.relationships}
        relation_id_parity = expected_relationship_ids == restored_relationship_ids
        cases.append(
            {
                "doc_id": record.doc_id,
                "company_id": graph.company_id,
                **asdict(quality),
                "backend_relation_id_parity": relation_id_parity,
                "missing_backend_relationships": len(
                    expected_relationship_ids - restored_relationship_ids
                ),
                "unexpected_backend_relationships": len(
                    restored_relationship_ids - expected_relationship_ids
                ),
                "passed": quality.passed and relation_id_parity,
            }
        )

    total_relationships = sum(int(item.get("relationship_count", 0)) for item in cases)
    missing_evidence = sum(int(item.get("missing_evidence_count", 0)) for item in cases)
    passed_count = sum(bool(item.get("passed")) for item in cases)
    report = {
        "total_documents": len(cases),
        "passed_documents": passed_count,
        "pass_rate": round(passed_count / max(len(cases), 1), 4),
        "total_relationships": total_relationships,
        "evidence_grounding_rate": round(
            (total_relationships - missing_evidence) / max(total_relationships, 1),
            4,
        ),
        "all_backend_roundtrips_match": all(
            bool(item.get("backend_relation_id_parity")) for item in cases
        ),
        "cases": cases,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, indent=2))
    return 0 if passed_count == len(cases) and cases else 2


if __name__ == "__main__":
    raise SystemExit(main())
