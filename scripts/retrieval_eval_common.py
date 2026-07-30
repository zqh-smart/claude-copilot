"""Shared L3/L4 retrieval eval helpers (doc resolution + case scoring)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SERVING_EVAL_DIR = Path(__file__).resolve().parents[1] / "data" / "reports" / "serving_eval"


def values_equal(actual: Any, expected: Any) -> bool:
    try:
        return abs(float(actual) - float(expected)) <= max(1.0, abs(float(expected)) * 0.001)
    except (TypeError, ValueError):
        return str(actual).strip() == str(expected).strip()


def _company_matches(expected: str | None, actual: str | None) -> bool:
    if not expected or not actual:
        return True
    return expected in actual or actual in expected


def _report_matches_expectations(
    report: dict,
    *,
    document_key: str | None,
    company: str | None,
    year: int | None,
) -> bool:
    if document_key and report.get("document_key") == document_key:
        return True
    summary = (report.get("serving_gate") or {}).get("summary") or {}
    report_company = summary.get("company")
    report_year = summary.get("year")
    if company and report_company and not _company_matches(company, report_company):
        return False
    if year is not None and report_year not in {None, year}:
        return False
    if company and report_company:
        return True
    if year is not None and report_year is not None:
        return True
    return document_key is None and company is None and year is None


def resolve_doc_id_from_expectations(
    *,
    doc_id: str | None,
    expectations: dict,
    serving_eval_dir: Path = SERVING_EVAL_DIR,
) -> str:
    if doc_id:
        return doc_id

    notes = expectations.get("notes") or {}
    company = notes.get("company")
    year = notes.get("year")
    document_key = expectations.get("document_key")

    if serving_eval_dir.exists():
        reports = sorted(
            serving_eval_dir.glob("*_serving_eval.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for report_path in reports:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if not _report_matches_expectations(
                report,
                document_key=document_key,
                company=company,
                year=year,
            ):
                continue
            resolved = report.get("doc_id")
            if resolved:
                return resolved

    from app.api import dependencies
    from src.claude_copilot.schemas.document import DocumentProcessingStatus

    for record in dependencies.get_document_service().list_documents():
        if record.status != DocumentProcessingStatus.COMPLETED:
            continue
        if company and record.metadata.company and not _company_matches(
            company, record.metadata.company
        ):
            continue
        if year is not None and record.metadata.year not in {None, year}:
            continue
        return record.doc_id

    raise FileNotFoundError(
        "No completed document found. Run serving ingest eval first or pass --doc-id."
    )


def graph_path_items(preview: Any) -> list[dict]:
    items: list[dict] = []
    for path in preview.graph_paths or []:
        if isinstance(path, dict):
            items.append(path)
            continue
        items.append(path.model_dump(mode="json") if hasattr(path, "model_dump") else {})
    return items


def score_retrieval_case(case: dict, preview: Any) -> dict:
    """L3-aligned retrieval scoring (route, metrics, semantic hits, graph relations)."""
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
    elif expect_route in {"graph", "relational"}:
        route_ok = "graph" in routes or intent in {"relational", "hybrid"}

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
            if case.get("expect_value") is not None and not values_equal(
                value, case["expect_value"]
            ):
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

    section_ok = True
    matched_section_types: list[str] = []
    if case.get("expect_section_types"):
        expected_sections = set(case["expect_section_types"])
        section_types = {
            str(section_type)
            for hit in (preview.hits or [])
            if (section_type := (hit.metadata or {}).get("section_type"))
        }
        matched_section_types = sorted(expected_sections & section_types)
        has_section_metadata = bool(section_types)
        if has_section_metadata:
            section_ok = bool(matched_section_types)
        elif case.get("expect_keywords"):
            section_ok = bool(keyword_hits)
        else:
            section_ok = len(preview.hits or []) > 0
        semantic_ok = semantic_ok and section_ok

    graph_paths = graph_path_items(preview)
    graph_ok = True
    matched_relations: list[str] = []
    if case.get("expect_graph_relation_types") or expect_route in {"graph", "relational"}:
        expected_types = set(case.get("expect_graph_relation_types") or [])
        for path in graph_paths:
            for rel in path.get("relationships") or []:
                rel_type = rel.get("relationship_type") if isinstance(rel, dict) else None
                if rel_type:
                    matched_relations.append(rel_type)
        if expected_types:
            graph_ok = bool(expected_types & set(matched_relations))
        else:
            graph_ok = len(graph_paths) > 0

    passed = bool(route_ok and metric_ok and semantic_ok and graph_ok and section_ok)
    return {
        "id": case.get("id"),
        "question": case.get("question"),
        "expect_route": expect_route,
        "actual_intent": intent,
        "actual_routes": routes,
        "route_ok": route_ok,
        "metric_ok": metric_ok,
        "semantic_ok": semantic_ok,
        "section_ok": section_ok,
        "graph_ok": graph_ok,
        "matched_metric": matched_metric,
        "matched_relations": sorted(set(matched_relations)),
        "matched_section_types": matched_section_types,
        "keyword_hits": keyword_hits,
        "hit_count": len(preview.hits or []),
        "metric_count": len(preview.metrics or []),
        "graph_path_count": len(graph_paths),
        "warnings": list(preview.warnings or []),
        "answer_preview": (preview.answer or "")[:400],
        "passed": passed,
    }
