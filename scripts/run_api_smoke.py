"""Lightweight HTTP API smoke for Knowledge Layer retrieval (TestClient)."""

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
SERVING_REPORT_DIR = ROOT / "data" / "reports" / "serving_eval"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HTTP API smoke (FastAPI TestClient)")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--pdf-path", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--doc-id", default="", help="Completed doc_id (skip ingest/discovery)")
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest smoke PDF via pipeline before API checks (slow; needs PDF)",
    )
    parser.add_argument("--storage-backend", default="postgres")
    parser.add_argument("--vector-backend", default="qdrant")
    parser.add_argument("--graph-backend", default="neo4j")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--allow-hash-fallback",
        action="store_true",
        help="Allow hash embedding fallback when Silicon is unavailable",
    )
    return parser.parse_args()


def _reset_caches() -> None:
    from app.api import dependencies
    from app.core.config import get_settings

    get_settings.cache_clear()
    for name in dir(dependencies):
        obj = getattr(dependencies, name)
        if callable(obj) and hasattr(obj, "cache_clear"):
            obj.cache_clear()


def _values_equal(actual, expected) -> bool:
    try:
        return abs(float(actual) - float(expected)) <= max(1.0, abs(float(expected)) * 0.001)
    except (TypeError, ValueError):
        return str(actual).strip() == str(expected).strip()


def _doc_id_from_serving_report() -> str | None:
    if not SERVING_REPORT_DIR.exists():
        return None
    reports = sorted(
        SERVING_REPORT_DIR.glob("*_serving_eval.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for report_path in reports:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        doc_id = payload.get("doc_id")
        if doc_id:
            return str(doc_id)
    return None


def _discover_doc_id(*, company: str, year: int) -> str | None:
    from app.api import dependencies
    from src.claude_copilot.schemas.document import DocumentProcessingStatus

    pipeline = dependencies.get_document_pipeline_service()
    matches = [
        record
        for record in pipeline.list_documents()
        if record.status == DocumentProcessingStatus.COMPLETED
        and record.metadata.company == company
        and record.metadata.year == year
    ]
    if not matches:
        return None
    return max(matches, key=lambda record: record.updated_at).doc_id


def _resolve_revenue_case(expectations: dict) -> dict:
    for case in expectations.get("retrieval_cases") or []:
        if case.get("id") == "q_revenue_2021":
            return case
    cases = expectations.get("retrieval_cases") or []
    if not cases:
        raise ValueError("golden has no retrieval_cases")
    return cases[0]


def _assert_research_case(payload: dict, case: dict) -> dict:
    analysis = payload.get("query_analysis") or {}
    intent = analysis.get("intent")
    routes = list(analysis.get("routes") or [])
    expect_route = case.get("expect_route")

    route_ok = True
    if expect_route == "structured":
        route_ok = intent == "structured" or "sql" in routes
    elif expect_route == "semantic":
        route_ok = intent == "semantic" or ("vector" in routes and "sql" not in routes)
    elif expect_route == "hybrid":
        route_ok = intent == "hybrid" or ("vector" in routes and "sql" in routes)
    elif expect_route in {"graph", "relational"}:
        route_ok = "graph" in routes or intent in {"relational", "hybrid"}

    metric_ok = True
    matched_metric = None
    if case.get("expect_metric_key"):
        metric_ok = False
        for metric in payload.get("metrics") or []:
            if metric.get("metric_key") != case["expect_metric_key"]:
                continue
            if case.get("expect_period") and str(metric.get("period")) != str(case["expect_period"]):
                continue
            value = metric.get("value")
            if case.get("expect_value") is not None and not _values_equal(value, case["expect_value"]):
                continue
            metric_ok = True
            matched_metric = {
                "metric_key": metric.get("metric_key"),
                "period": metric.get("period"),
                "value": value,
            }
            break

    passed = bool(route_ok and metric_ok)
    return {
        "case_id": case.get("id"),
        "question": case.get("question"),
        "route_ok": route_ok,
        "metric_ok": metric_ok,
        "actual_intent": intent,
        "actual_routes": routes,
        "matched_metric": matched_metric,
        "passed": passed,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    expectations = json.loads(args.golden.read_text(encoding="utf-8"))
    notes = expectations.get("notes") or {}
    company = notes.get("company") or "北京指南针科技发展股份有限公司"
    year = int(notes.get("year") or 2021)
    revenue_case = _resolve_revenue_case(expectations)

    os.environ["STORAGE_BACKEND"] = args.storage_backend
    os.environ["VECTOR_STORE_BACKEND"] = args.vector_backend
    os.environ["GRAPH_STORE_BACKEND"] = args.graph_backend
    os.environ["LLM_GROUNDED_SYNTHESIS_ENABLED"] = "false"
    _reset_caches()

    from fastapi.testclient import TestClient

    from app.api import dependencies
    from app.core.config import get_settings
    from app.core.db import build_company_id
    from app.main import app
    from src.claude_copilot.schemas.document import DocumentProcessingStatus

    settings = get_settings()
    embedding_info: dict = {"embedding_backend": settings.embedding_backend}
    if settings.embedding_backend in {"auto", "silicon"} and not args.allow_hash_fallback:
        try:
            import httpx

            response = httpx.post(
                f"{settings.silicon_base_url.rstrip('/')}/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.silicon_key}",
                    "Content-Type": "application/json",
                },
                json={"model": settings.embedding_model_id, "input": ["ping"]},
                timeout=15,
            )
            embedding_info["silicon_ok"] = response.status_code == 200
        except Exception as exc:  # noqa: BLE001
            embedding_info["silicon_error"] = f"{type(exc).__name__}: {exc}"
            embedding_info["silicon_ok"] = False
    elif args.allow_hash_fallback:
        os.environ["EMBEDDING_BACKEND"] = "hash"
        os.environ["RERANK_BACKEND"] = "deterministic"
        os.environ.setdefault("QDRANT_COLLECTION_NAME", "document_segments_hash_serving")
        embedding_info["fallback"] = "hash+deterministic"
        _reset_caches()
        settings = get_settings()

    doc_id = args.doc_id.strip()
    ingest_seconds: float | None = None
    if args.ingest:
        if not args.pdf_path.exists():
            print(f"MISSING_PDF {args.pdf_path}")
            return 1
        pipeline = dependencies.get_document_pipeline_service()
        t0 = time.perf_counter()
        record = pipeline.ingest(
            filename=args.pdf_path.name,
            content_type="application/pdf",
            content=args.pdf_path.read_bytes(),
            company=company,
            year=year,
            doc_type="annual_report",
            source="api_smoke",
            industry="金融信息服务",
            company_aliases=["指南针", "300803"],
        )
        ingest_seconds = round(time.perf_counter() - t0, 3)
        if record.status != DocumentProcessingStatus.COMPLETED:
            print(
                json.dumps(
                    {
                        "ingest_failed": True,
                        "doc_id": record.doc_id,
                        "status": str(record.status),
                        "error": record.error_message,
                    },
                    ensure_ascii=False,
                )
            )
            return 1
        doc_id = record.doc_id
    elif not doc_id:
        doc_id = _discover_doc_id(company=company, year=year) or ""
    if not doc_id:
        doc_id = _doc_id_from_serving_report() or ""
    if not doc_id:
        print(
            "PREREQUISITE: no completed doc found. Run serving ingest first, pass --doc-id, "
            "or use --ingest with the smoke PDF.\n"
            "  python scripts/run_serving_ingest_eval.py\n"
            "  python scripts/run_api_smoke.py --doc-id <doc_id>"
        )
        return 1

    company_id = build_company_id(company)
    checks: list[dict] = []
    t0 = time.perf_counter()

    with TestClient(app) as client:
        health = client.get("/health")
        health_ok = health.status_code == 200 and health.json().get("status") == "ok"
        checks.append(
            {
                "name": "health",
                "passed": health_ok,
                "status_code": health.status_code,
                "body": health.json(),
            }
        )

        companies = client.get("/api/v1/companies")
        companies_payload = companies.json() if companies.status_code == 200 else []
        company_row = next(
            (item for item in companies_payload if item.get("company_id") == company_id),
            None,
        )
        companies_ok = companies.status_code == 200 and company_row is not None
        checks.append(
            {
                "name": "companies",
                "passed": companies_ok,
                "status_code": companies.status_code,
                "company_id": company_id,
                "found": company_row is not None,
            }
        )

        metrics = client.get(
            f"/api/v1/companies/{company_id}/metrics",
            params={"metric_key": "revenue", "year": year},
        )
        metrics_items = metrics.json().get("items", []) if metrics.status_code == 200 else []
        revenue_metric = next(
            (
                item
                for item in metrics_items
                if item.get("metric_key") == "revenue"
                and (item.get("period_year") == year or str(item.get("period")) == str(year))
            ),
            None,
        )
        metrics_ok = (
            metrics.status_code == 200
            and revenue_metric is not None
            and _values_equal(revenue_metric.get("value"), revenue_case["expect_value"])
        )
        checks.append(
            {
                "name": "company_metrics_revenue",
                "passed": metrics_ok,
                "status_code": metrics.status_code,
                "matched_metric": revenue_metric,
                "expect_value": revenue_case.get("expect_value"),
            }
        )

        research = client.post(
            "/api/v1/research/query",
            json={
                "doc_id": doc_id,
                "question": revenue_case["question"],
                "top_k": args.top_k,
            },
        )
        research_payload = research.json() if research.status_code == 200 else {}
        research_assert = (
            _assert_research_case(research_payload, revenue_case)
            if research.status_code == 200
            else {"passed": False, "case_id": revenue_case.get("id")}
        )
        checks.append(
            {
                "name": "research_query_revenue",
                "passed": research.status_code == 200 and research_assert["passed"],
                "status_code": research.status_code,
                **research_assert,
            }
        )

    elapsed = round(time.perf_counter() - t0, 3)
    report = {
        "doc_id": doc_id,
        "company": company,
        "company_id": company_id,
        "year": year,
        "ingest_seconds": ingest_seconds,
        "api_seconds": elapsed,
        "backends": {
            "storage": settings.storage_backend,
            "vector": settings.vector_store_backend,
            "graph": settings.graph_store_backend,
            "embedding": settings.embedding_backend,
            "qdrant_collection": settings.qdrant_collection_name,
        },
        "embedding_info": embedding_info,
        "checks": checks,
        "passed": all(item["passed"] for item in checks),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
