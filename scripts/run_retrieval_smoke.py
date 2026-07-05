from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api import dependencies
from src.claude_copilot.schemas.document import DocumentProcessingStatus


@dataclass
class RetrievalHitSummary:
    segment_id: str
    score: float
    content_preview: str


@dataclass
class RetrievalDocSummary:
    doc_id: str
    source: str | None
    filename: str
    question: str
    hit_count: int
    hits: list[RetrievalHitSummary]


def resolve_question(source: str | None, filename: str) -> str:
    source = source or ""
    name = filename.lower()

    if source == "docker_smoke" or "docker_smoke" in name:
        return "What risk factors are mentioned in the document?"
    if source == "qdrant_smoke" or "qdrant_smoke" in name:
        return "What does the document say about liquidity pressure and capital ratios?"
    if source == "silicon_smoke_valid" or "silicon_smoke" in name:
        return "What does the document say about liquidity risk and credit losses?"
    return "What are the key financial risks and performance signals in the document?"


def main() -> int:
    document_service = dependencies.get_document_service()
    research_service = dependencies.get_research_service()

    summaries: list[RetrievalDocSummary] = []
    for record in document_service.list_documents():
        if record.status != DocumentProcessingStatus.COMPLETED:
            continue

        question = resolve_question(record.metadata.source, record.filename)
        preview = research_service.preview(
            doc_id=record.doc_id,
            question=question,
            top_k=3,
        )
        hits = [
            RetrievalHitSummary(
                segment_id=hit.segment_id,
                score=round(hit.score, 4),
                content_preview=hit.content[:200],
            )
            for hit in preview.hits
        ]
        summaries.append(
            RetrievalDocSummary(
                doc_id=record.doc_id,
                source=record.metadata.source,
                filename=record.filename,
                question=question,
                hit_count=len(hits),
                hits=hits,
            )
        )

    report_dir = ROOT_DIR / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "historical_retrieval_smoke_report.json"
    payload = {
        "summary": {
            "completed_docs": len(summaries),
            "docs_with_hits": sum(1 for item in summaries if item.hit_count > 0),
        },
        "documents": [
            {
                **asdict(item),
                "hits": [asdict(hit) for hit in item.hits],
            }
            for item in summaries
        ],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for item in summaries:
        print(f"DOC {item.doc_id} source={item.source} hits={item.hit_count}")
        print(f"Q: {item.question}")
        for hit in item.hits:
            print(f"  - {hit.segment_id} score={hit.score} text={hit.content_preview}")

    print(f"REPORT {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
