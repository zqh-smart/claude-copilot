"""Serving-track ingest (Postgres/Qdrant/Neo4j) + L3 retrieval_cases eval."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PDF = Path(
    r"Z:/BaiduNetdiskDownload/阶段12：LLM大型复杂项目实战"
    r"/项目实战2：大模型金融对话交互系统/allpdf-part1"
    r"/2022-01-25__北京指南针科技发展股份有限公司__300803__指南针__2021年__年度报告.pdf"
)
DEFAULT_GOLDEN = ROOT / "data" / "golden" / "znz_2021_stage_expectations.json"
OUT_DIR = ROOT / "data" / "reports" / "serving_eval"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serving ingest + L3 retrieval eval")
    parser.add_argument("--pdf-path", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--expectations", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--storage-backend", default="postgres")
    parser.add_argument("--vector-backend", default="qdrant")
    parser.add_argument("--graph-backend", default="neo4j")
    parser.add_argument("--top-k", type=int, default=5)
    return parser.parse_args()


def _reset_caches() -> None:
    from app.api import dependencies
    from app.core.config import get_settings

    get_settings.cache_clear()
    for name in dir(dependencies):
        obj = getattr(dependencies, name)
        if callable(obj) and hasattr(obj, "cache_clear"):
            obj.cache_clear()


def _ensure_embedding_backend() -> dict:
    from app.core.config import get_settings

    settings = get_settings()
    info = {
        "requested_embedding": settings.embedding_backend,
        "fallback": None,
        "silicon_ok": False,
    }
    if settings.embedding_backend in {"auto", "silicon"} and settings.silicon_key:
        try:
            import httpx

            response = httpx.post(
                f"{settings.silicon_base_url.rstrip('/')}/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.silicon_key}",
                    "Content-Type": "application/json",
                },
                json={"model": settings.embedding_model_id, "input": ["ping"]},
                timeout=20,
            )
            info["silicon_ok"] = response.status_code < 500
        except Exception as exc:  # noqa: BLE001
            info["silicon_error"] = type(exc).__name__
    if settings.embedding_backend in {"auto", "silicon"} and not info["silicon_ok"]:
        os.environ["EMBEDDING_BACKEND"] = "hash"
        os.environ["RERANK_BACKEND"] = "deterministic"
        os.environ.setdefault("QDRANT_COLLECTION_NAME", "document_segments_hash_serving")
        info["fallback"] = "hash+deterministic"
        _reset_caches()
    return info


def _values_equal(actual, expected) -> bool:
    try:
        return abs(float(actual) - float(expected)) <= max(1.0, abs(float(expected)) * 0.001)
    except (TypeError, ValueError):
        return str(actual).strip() == str(expected).strip()


def _score_case(case: dict, preview) -> dict:
    expect_route = case.get("expect_route")
    analysis = preview.query_analysis
    intent = analysis.intent if analysis else None
    routes = list(analysis.routes) if analysis else []

    route_ok = True
    if expect_route == "structured":
        route_ok = intent == "structured" or "sql" in routes
    elif expect_route == "semantic":
        route_ok = intent == "semantic" or ("vector" in routes and "sql" not in routes)
    elif expect_route == "hybrid":
        route_ok = intent == "hybrid" or ("vector" in routes and "sql" in routes)

    metric_ok = True
    matched_metric = None
    if case.get("expect_metric_key"):
        metric_ok = False
        for metric in preview.metrics or []:
            key = getattr(metric, "metric_key", None) or (
                metric.get("metric_key") if isinstance(metric, dict) else None
            )
            period = getattr(metric, "period", None) or (
                metric.get("period") if isinstance(metric, dict) else None
            )
            value = getattr(metric, "value", None) or (
                metric.get("value") if isinstance(metric, dict) else None
            )
            if key != case["expect_metric_key"]:
                continue
            if case.get("expect_period") and str(period) != str(case["expect_period"]):
                continue
            if case.get("expect_value") is not None and not _values_equal(value, case["expect_value"]):
                continue
            metric_ok = True
            matched_metric = {"metric_key": key, "period": period, "value": value}
            break

    semantic_ok = True
    keyword_hits: list[str] = []
    if case.get("expect_keywords"):
        semantic_ok = False
        blob = "\n".join(hit.content for hit in (preview.hits or []))
        keyword_hits = [kw for kw in case["expect_keywords"] if kw in blob]
        semantic_ok = bool(keyword_hits)
    if case.get("expect_section_types"):
        section_types = {
            (hit.metadata or {}).get("section_type")
            for hit in (preview.hits or [])
            if getattr(hit, "metadata", None)
        }
        # Also accept keyword proxy when section metadata sparse.
        if not (set(case["expect_section_types"]) & section_types) and not keyword_hits:
            if case.get("expect_keywords"):
                semantic_ok = bool(keyword_hits)
            else:
                # soft: require at least one hit for semantic/hybrid narrative
                semantic_ok = semantic_ok and len(preview.hits or []) > 0

    passed = bool(route_ok and metric_ok and semantic_ok)
    return {
        "id": case.get("id"),
        "question": case.get("question"),
        "expect_route": expect_route,
        "actual_intent": intent,
        "actual_routes": routes,
        "route_ok": route_ok,
        "metric_ok": metric_ok,
        "semantic_ok": semantic_ok,
        "matched_metric": matched_metric,
        "keyword_hits": keyword_hits,
        "hit_count": len(preview.hits or []),
        "metric_count": len(preview.metrics or []),
        "passed": passed,
        "warnings": list(preview.warnings or []),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    if not args.pdf_path.exists():
        raise FileNotFoundError(args.pdf_path)
    expectations = json.loads(args.expectations.read_text(encoding="utf-8"))

    os.environ["STORAGE_BACKEND"] = args.storage_backend
    os.environ["VECTOR_STORE_BACKEND"] = args.vector_backend
    os.environ["GRAPH_STORE_BACKEND"] = args.graph_backend
    _reset_caches()
    embedding_info = _ensure_embedding_backend()

    from app.api import dependencies
    from app.core.config import get_settings
    from app.core.db import build_company_id, select_serving_metric_facts_from_document
    from src.claude_copilot.schemas.document import DocumentProcessingStatus

    settings = get_settings()
    print(
        json.dumps(
            {
                "storage_backend": settings.storage_backend,
                "vector_store_backend": settings.vector_store_backend,
                "graph_store_backend": settings.graph_store_backend,
                "embedding_backend": settings.embedding_backend,
                "qdrant_collection": settings.qdrant_collection_name,
                "embedding_info": embedding_info,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    pipeline = dependencies.get_document_pipeline_service()
    research = dependencies.get_research_service()
    financial = dependencies.get_financial_data_repository()
    parsed_repo = dependencies.get_parsed_document_repository()

    t0 = time.perf_counter()
    record = pipeline.ingest(
        filename=args.pdf_path.name,
        content_type="application/pdf",
        content=args.pdf_path.read_bytes(),
        company=expectations.get("notes", {}).get("company") or "北京指南针科技发展股份有限公司",
        year=expectations.get("notes", {}).get("year") or 2021,
        doc_type="annual_report",
        source="serving_ingest_eval",
        industry="金融信息服务",
        company_aliases=["指南针", "300803"],
    )
    ingest_seconds = round(time.perf_counter() - t0, 3)
    print(
        {
            "status": record.status,
            "doc_id": record.doc_id,
            "segments": record.segment_count,
            "ingest_seconds": ingest_seconds,
            "error": record.error_message,
        }
    )
    if record.status != DocumentProcessingStatus.COMPLETED:
        return 1

    parsed = parsed_repo.get(record.doc_id)
    gate = (parsed.financial_schema.metadata.get("serving_gate") if parsed.financial_schema else {}) or {}
    serving_facts = select_serving_metric_facts_from_document(parsed)
    company_id = build_company_id(record.metadata.company or "")
    sql_metrics = financial.query_metrics(company_id, limit=500) if company_id else []

    cases = expectations.get("retrieval_cases") or []
    case_results = []
    for case in cases:
        preview = research.preview(doc_id=record.doc_id, question=case["question"], top_k=args.top_k)
        scored = _score_case(case, preview)
        case_results.append(scored)
        print(json.dumps(scored, ensure_ascii=False, indent=2))

    passed = sum(1 for item in case_results if item["passed"])
    report = {
        "doc_id": record.doc_id,
        "ingest_seconds": ingest_seconds,
        "segment_count": record.segment_count,
        "serving_gate": gate,
        "serving_metric_fact_count": len(serving_facts),
        "sql_metric_count": len(sql_metrics),
        "company_id": company_id,
        "backends": {
            "storage": settings.storage_backend,
            "vector": settings.vector_store_backend,
            "graph": settings.graph_store_backend,
            "embedding": settings.embedding_backend,
            "qdrant_collection": settings.qdrant_collection_name,
        },
        "l3": {
            "total": len(case_results),
            "passed": passed,
            "pass_rate": round(passed / max(len(case_results), 1), 4),
            "cases": case_results,
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{record.doc_id}_serving_eval.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(out_path), "l3_pass_rate": report["l3"]["pass_rate"]}, ensure_ascii=False, indent=2))

    if not gate.get("allow_metric_serving", False):
        return 3
    if case_results and passed < len(case_results):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
