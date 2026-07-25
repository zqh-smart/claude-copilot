"""Ingest one annual report with production-like backends and run retrieval preview."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Prefer Qdrant + Silicon embeddings; use local JSON docs if Postgres is down.
os.environ.setdefault("VECTOR_STORE_BACKEND", "qdrant")
os.environ.setdefault("EMBEDDING_BACKEND", "silicon")
os.environ["STORAGE_BACKEND"] = os.environ.get("SMOKE_STORAGE_BACKEND", "local")

from app.api import dependencies
from app.core.config import get_settings
from src.claude_copilot.schemas.document import DocumentProcessingStatus


def _reset_dependency_caches() -> None:
    get_settings.cache_clear()
    for name in dir(dependencies):
        obj = getattr(dependencies, name)
        if callable(obj) and hasattr(obj, "cache_clear"):
            obj.cache_clear()


def _silicon_reachable() -> bool:
    try:
        import httpx

        settings = get_settings()
        if not settings.silicon_key:
            return False
        response = httpx.post(
            f"{settings.silicon_base_url.rstrip('/')}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.silicon_key}",
                "Content-Type": "application/json",
            },
            json={"model": settings.embedding_model_id, "input": ["ping"]},
            timeout=20,
        )
        return response.status_code < 500
    except Exception:
        return False

PDF_PATH = Path(
    r"Z:/BaiduNetdiskDownload/阶段12：LLM大型复杂项目实战"
    r"/项目实战2：大模型金融对话交互系统/allpdf-part1"
    r"/2022-01-25__北京指南针科技发展股份有限公司__300803__指南针__2021年__年度报告.pdf"
)
OUT = ROOT / "data" / "reports" / "full_pipeline_eval" / "指南针_2021_retrieval_smoke.json"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    _reset_dependency_caches()
    silicon_ok = _silicon_reachable()
    if not silicon_ok:
        # Keep Qdrant path real; fall back embedding/rerank when Silicon SSL/network is down.
        os.environ["EMBEDDING_BACKEND"] = "hash"
        os.environ["RERANK_BACKEND"] = "deterministic"
        os.environ["QDRANT_COLLECTION_NAME"] = "document_segments_hash_smoke"
        _reset_dependency_caches()
    settings = get_settings()
    print(
        {
            "storage_backend": settings.storage_backend,
            "vector_store_backend": settings.vector_store_backend,
            "embedding_backend": settings.embedding_backend,
            "silicon_reachable": silicon_ok,
            "qdrant_url": settings.qdrant_url,
            "qdrant_collection": settings.qdrant_collection_name,
            "silicon_key_set": bool(settings.silicon_key),
        }
    )

    if not PDF_PATH.exists():
        raise FileNotFoundError(PDF_PATH)

    pipeline = dependencies.get_document_pipeline_service()
    research_service = dependencies.get_research_service()

    record = pipeline.ingest(
        filename=PDF_PATH.name,
        content_type="application/pdf",
        content=PDF_PATH.read_bytes(),
        company="北京指南针科技发展股份有限公司",
        year=2021,
        doc_type="annual_report",
        source="prod_retrieval_smoke",
        industry="金融信息服务",
        company_aliases=["指南针", "300803"],
    )
    print({"status": record.status, "doc_id": record.doc_id, "segments": record.segment_count, "error": record.error_message})
    if record.status != DocumentProcessingStatus.COMPLETED:
        return 1

    questions = [
        "公司的营业收入和净利润是多少？",
        "管理层讨论与分析提到了哪些主要风险？",
        "经营活动产生的现金流量净额是多少？",
    ]
    results = []
    for question in questions:
        preview = research_service.preview(doc_id=record.doc_id, question=question, top_k=5)
        results.append(
            {
                "question": question,
                "answer_preview": (preview.answer or "")[:400],
                "hit_count": len(preview.hits),
                "hits": [
                    {
                        "segment_id": hit.segment_id,
                        "score": round(hit.score, 4),
                        "preview": hit.content[:220].replace("\n", " "),
                    }
                    for hit in preview.hits
                ],
                "metrics": [m.model_dump() if hasattr(m, "model_dump") else m for m in (preview.metrics or [])][:5],
                "graph_paths": len(getattr(preview, "graph_paths", []) or []),
            }
        )
        print(json.dumps(results[-1], ensure_ascii=False, indent=2))

    payload = {
        "doc_id": record.doc_id,
        "segment_count": record.segment_count,
        "settings": {
            "storage_backend": settings.storage_backend,
            "vector_store_backend": settings.vector_store_backend,
            "embedding_backend": settings.embedding_backend,
        },
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
