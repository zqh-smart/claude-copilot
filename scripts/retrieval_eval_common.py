"""Shared L3/L4 retrieval eval helpers (doc resolution + case scoring)."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

SERVING_EVAL_DIR = Path(__file__).resolve().parents[1] / "data" / "reports" / "serving_eval"


def values_equal(actual: Any, expected: Any) -> bool:
    try:
        return abs(float(actual) - float(expected)) <= max(1.0, abs(float(expected)) * 0.001)
    except (TypeError, ValueError):
        return str(actual).strip() == str(expected).strip()


def periods_equal(actual: Any, expected: Any) -> bool:
    actual_text = str(actual).strip()
    expected_text = str(expected).strip()
    if actual_text == expected_text:
        return True

    def single_year(value: str) -> str | None:
        years = set(re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", value))
        return years.pop() if len(years) == 1 else None

    actual_year = single_year(actual_text)
    expected_year = single_year(expected_text)
    return actual_year is not None and actual_year == expected_year


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
        if (
            company
            and record.metadata.company
            and not _company_matches(company, record.metadata.company)
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


CHANNEL_ABLATION_SETS: dict[str, list[str]] = {
    "vector_only": ["vector"],
    "sql_only": ["sql"],
    "graph_only": ["graph"],
    "vector_sql": ["vector", "sql"],
    "vector_graph": ["vector", "graph"],
    "all_hybrid": ["vector", "sql", "graph"],
}


def load_retrieval_eval_cases(
    expectations: dict,
    *,
    include_benchmark: bool = False,
    case_ids: list[str] | None = None,
) -> list[dict]:
    """Load gate cases; optionally append joint-benchmark expansion cases."""
    cases = list(expectations.get("retrieval_cases") or [])
    if include_benchmark:
        cases.extend(list(expectations.get("benchmark_cases") or []))
    if case_ids:
        allowed = set(case_ids)
        cases = [case for case in cases if case.get("id") in allowed]
    return cases


def _explicit_relevant_set(case: dict) -> set[str]:
    ids = {str(item) for item in (case.get("expect_relevant_segment_ids") or [])}
    fingerprints = {
        str(item) for item in (case.get("expect_relevant_segment_fingerprints") or [])
    }
    return ids | fingerprints


def _hit_relevance(case: dict, hit: Any) -> tuple[int, str | None]:
    expected_ids = set(case.get("expect_relevant_segment_ids") or [])
    if expected_ids:
        return int(getattr(hit, "segment_id", None) in expected_ids), "explicit_segment_ids"

    expected_fingerprints = set(case.get("expect_relevant_segment_fingerprints") or [])
    if expected_fingerprints:
        metadata = getattr(hit, "metadata", None) or {}
        return (
            int(metadata.get("segment_fingerprint") in expected_fingerprints),
            "explicit_segment_fingerprints",
        )

    expected_sections = set(case.get("expect_section_types") or [])
    expected_keywords = [str(item).casefold() for item in case.get("expect_keywords") or []]
    if not expected_sections and not expected_keywords:
        return 0, None

    metadata = getattr(hit, "metadata", None) or {}
    section_match = not expected_sections or metadata.get("section_type") in expected_sections
    content = str(getattr(hit, "content", "")).casefold()
    keyword_match = not expected_keywords or any(item in content for item in expected_keywords)
    if expected_sections and expected_keywords:
        return int(section_match) * 2 + int(keyword_match), "semantic_proxy"
    return int(section_match and keyword_match), "semantic_proxy"


def _ndcg(relevance: list[int]) -> float:
    if not relevance:
        return 0.0
    dcg = sum(value / math.log2(index + 1) for index, value in enumerate(relevance, start=1))
    ideal = sorted(relevance, reverse=True)
    idcg = sum(value / math.log2(index + 1) for index, value in enumerate(ideal, start=1))
    return round(dcg / idcg, 4) if idcg else 0.0


def _ranking_at_k(
    case: dict,
    hits: list[Any],
    *,
    k: int,
    source: str | None,
) -> dict[str, Any]:
    relevance: list[int] = []
    hard_negative_fingerprints = set(
        case.get("expect_hard_negative_segment_fingerprints") or []
    )
    hard_negative_ranks: list[int] = []
    found_explicit: set[str] = set()
    expected_explicit = _explicit_relevant_set(case)

    for rank, hit in enumerate(hits[:k], start=1):
        relevance_grade, _ = _hit_relevance(case, hit)
        relevance.append(relevance_grade)
        metadata = getattr(hit, "metadata", None) or {}
        fingerprint = metadata.get("segment_fingerprint")
        segment_id = getattr(hit, "segment_id", None)
        if fingerprint in hard_negative_fingerprints:
            hard_negative_ranks.append(rank)
        if fingerprint and fingerprint in expected_explicit:
            found_explicit.add(str(fingerprint))
        if segment_id and str(segment_id) in expected_explicit:
            found_explicit.add(str(segment_id))

    relevant_ranks = [index for index, value in enumerate(relevance, start=1) if value > 0]
    reciprocal_rank = 1.0 / relevant_ranks[0] if relevant_ranks else 0.0
    recall = None
    if source and str(source).startswith("explicit_segment_") and expected_explicit:
        recall = round(len(found_explicit) / len(expected_explicit), 4)

    return {
        "relevant_hit_ranks": relevant_ranks,
        "relevance_grades": relevance,
        "hit_rate": float(bool(relevant_ranks)),
        "reciprocal_rank": round(reciprocal_rank, 4),
        "ndcg": _ndcg(relevance),
        "recall": recall,
        "hard_negative_hit_ranks": hard_negative_ranks,
        "hard_negative_rate": float(bool(hard_negative_ranks)),
    }


def _ranking_diagnostics(case: dict, hits: list[Any], *, k: int = 10) -> dict[str, Any]:
    source: str | None = None
    for hit in hits[:k]:
        _, hit_source = _hit_relevance(case, hit)
        if hit_source:
            source = hit_source
            break
    # Also detect labels even when no hits matched (for recall=0 reporting).
    if source is None and _explicit_relevant_set(case):
        source = (
            "explicit_segment_ids"
            if case.get("expect_relevant_segment_ids")
            else "explicit_segment_fingerprints"
        )
    elif source is None and (
        case.get("expect_section_types") or case.get("expect_keywords")
    ):
        source = "semantic_proxy"

    at_5 = _ranking_at_k(case, hits, k=5, source=source)
    at_10 = _ranking_at_k(case, hits, k=10, source=source)

    if source is None:
        return {
            "evaluated": False,
            "relevance_source": None,
            "relevant_hit_ranks": [],
            "relevance_grades": [],
            "hit_rate_at_5": None,
            "reciprocal_rank": None,
            "ndcg_at_5": None,
            "recall_at_5": None,
            "mrr_at_10": None,
            "ndcg_at_10": None,
            "hard_negative_hit_ranks": at_5["hard_negative_hit_ranks"],
            "hard_negative_rate_at_5": at_5["hard_negative_rate"],
            "hard_negative_rate_at_10": at_10["hard_negative_rate"],
        }

    return {
        "evaluated": True,
        "relevance_source": source,
        "relevant_hit_ranks": at_10["relevant_hit_ranks"],
        "relevance_grades": at_10["relevance_grades"],
        "hit_rate_at_5": at_5["hit_rate"],
        "reciprocal_rank": at_5["reciprocal_rank"],  # backward-compat alias for MRR@5
        "ndcg_at_5": at_5["ndcg"],
        "recall_at_5": at_5["recall"],
        "mrr_at_5": at_5["reciprocal_rank"],
        "mrr_at_10": at_10["reciprocal_rank"],
        "ndcg_at_10": at_10["ndcg"],
        "hard_negative_hit_ranks": at_10["hard_negative_hit_ranks"],
        "hard_negative_rate_at_5": at_5["hard_negative_rate"],
        "hard_negative_rate_at_10": at_10["hard_negative_rate"],
    }


def _hit_references(hits: list[Any], *, k: int = 10) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for rank, hit in enumerate(hits[:k], start=1):
        metadata = getattr(hit, "metadata", None) or {}
        content = " ".join(str(getattr(hit, "content", "")).split())
        references.append(
            {
                "rank": rank,
                "segment_id": getattr(hit, "segment_id", None),
                "score": getattr(hit, "score", None),
                "section_type": metadata.get("section_type"),
                "segment_fingerprint": metadata.get("segment_fingerprint"),
                "page_start": metadata.get("page_start"),
                "page_end": metadata.get("page_end"),
                "content_preview": content[:240],
            }
        )
    return references


def summarize_retrieval_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    ranking_cases = [item["ranking"] for item in cases if item["ranking"]["evaluated"]]
    explicit_cases = [
        item
        for item in ranking_cases
        if str(item["relevance_source"]).startswith("explicit_segment_")
    ]
    route_combinations = Counter(
        "+".join(item.get("actual_routes") or []) or "none" for item in cases
    )
    route_sets = [set(item.get("actual_routes") or []) for item in cases]
    channel_sets = {
        "vector_only": {"vector"},
        "sql_only": {"sql"},
        "graph_only": {"graph"},
        "vector_sql": {"vector", "sql"},
        "vector_graph": {"vector", "graph"},
        "all_channels": {"vector", "sql", "graph"},
    }
    failures = Counter(
        category for item in cases for category in item.get("failure_categories") or []
    )
    abstain_cases = [item for item in cases if item.get("expect_abstain")]
    latencies = [
        float(item["latency_ms"])
        for item in cases
        if item.get("latency_ms") is not None
    ]

    def mean(name: str, rows: list[dict[str, Any]] | None = None) -> float | None:
        pool = rows if rows is not None else ranking_cases
        values = [float(item[name]) for item in pool if item.get(name) is not None]
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    def percentile(values: list[float], pct: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
        return round(ordered[index], 2)

    return {
        "ranking": {
            "evaluated_cases": len(ranking_cases),
            "explicit_relevance_cases": len(explicit_cases),
            "semantic_proxy_cases": sum(
                item["relevance_source"] == "semantic_proxy" for item in ranking_cases
            ),
            "hit_rate_at_5": mean("hit_rate_at_5"),
            "mrr_at_5": (
                mean("mrr_at_5")
                if any(item.get("mrr_at_5") is not None for item in ranking_cases)
                else mean("reciprocal_rank")
            ),
            "ndcg_at_5": mean("ndcg_at_5"),
            "recall_at_5": mean("recall_at_5", explicit_cases),
            "mrr_at_10": mean("mrr_at_10"),
            "ndcg_at_10": mean("ndcg_at_10"),
            "hard_negative_rate_at_5": mean("hard_negative_rate_at_5"),
            "hard_negative_rate_at_10": mean("hard_negative_rate_at_10"),
            "note": (
                "recall_at_5 / mrr_at_10 / ndcg_at_10 use explicit fingerprint|id labels only "
                "where present; semantic_proxy rows are excluded from recall_at_5."
            ),
        },
        "abstention": {
            "evaluated_cases": len(abstain_cases),
            "accuracy": (
                round(
                    sum(1 for item in abstain_cases if item.get("abstain_ok"))
                    / max(len(abstain_cases), 1),
                    4,
                )
                if abstain_cases
                else None
            ),
        },
        "latency_ms": {
            "count": len(latencies),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
        },
        "route_combinations": dict(sorted(route_combinations.items())),
        "route_coverage_ablation": {
            name: {
                "covered": sum(routes <= channels for routes in route_sets),
                "total": len(route_sets),
            }
            for name, channels in channel_sets.items()
        },
        "failure_categories": dict(sorted(failures.items())),
    }


def summarize_channel_ablation(
    ablation_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate true channel-off ablation results (forced routes per case)."""
    by_channel: dict[str, list[dict[str, Any]]] = {}
    for row in ablation_rows:
        by_channel.setdefault(str(row["channel"]), []).append(row)
    summary: dict[str, Any] = {}
    for channel, rows in sorted(by_channel.items()):
        passed = sum(1 for row in rows if row.get("passed"))
        summary[channel] = {
            "total": len(rows),
            "passed": passed,
            "pass_rate": round(passed / max(len(rows), 1), 4),
            "routes": list(CHANNEL_ABLATION_SETS.get(channel, [])),
        }
    return summary


def score_retrieval_case(case: dict, preview: Any) -> dict:
    """L3-aligned retrieval scoring (route, metrics, semantic hits, graph relations)."""
    expect_route = case.get("expect_route")
    expect_abstain = bool(case.get("expect_abstain"))
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
    elif expect_route == "abstain":
        route_ok = True

    metric_ok = True
    matched_metric = None
    if case.get("expect_metric_key") and not expect_abstain:
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
            if case.get("expect_period") and not periods_equal(period, case["expect_period"]):
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
    if case.get("expect_keywords") and not expect_abstain:
        semantic_ok = False
        blob = "\n".join(hit.content for hit in (preview.hits or []))
        folded_blob = blob.casefold()
        keyword_hits = [kw for kw in case["expect_keywords"] if str(kw).casefold() in folded_blob]
        semantic_ok = bool(keyword_hits)

    section_ok = True
    matched_section_types: list[str] = []
    if case.get("expect_section_types") and not expect_abstain:
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
    if (
        case.get("expect_graph_relation_types") or expect_route in {"graph", "relational"}
    ) and not expect_abstain:
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

    # Abstain: must not return authoritative metrics / graph paths; vector noise alone is ok
    # only when no structured/graph evidence is attached.
    abstain_ok = True
    if expect_abstain:
        has_metrics = bool(preview.metrics)
        has_graph = bool(graph_paths)
        has_value_claim = bool(matched_metric)
        abstain_ok = not (has_metrics or has_graph or has_value_claim)
        metric_ok = True
        semantic_ok = True
        section_ok = True
        graph_ok = True

    ranking = _ranking_diagnostics(case, list(preview.hits or []))
    failure_categories = []
    if not route_ok:
        failure_categories.append("routing")
    if not metric_ok:
        failure_categories.append("structured_metric")
    if not semantic_ok:
        failure_categories.append("semantic_recall")
    if not section_ok:
        failure_categories.append("section_metadata")
    if not graph_ok:
        failure_categories.append("graph_path")
    if expect_abstain and not abstain_ok:
        failure_categories.append("abstention")
    passed = bool(
        route_ok and metric_ok and semantic_ok and graph_ok and section_ok and abstain_ok
    )
    return {
        "id": case.get("id"),
        "question": case.get("question"),
        "expect_route": expect_route,
        "expect_abstain": expect_abstain,
        "actual_intent": intent,
        "actual_routes": routes,
        "route_ok": route_ok,
        "metric_ok": metric_ok,
        "semantic_ok": semantic_ok,
        "section_ok": section_ok,
        "graph_ok": graph_ok,
        "abstain_ok": abstain_ok,
        "matched_metric": matched_metric,
        "matched_relations": sorted(set(matched_relations)),
        "matched_section_types": matched_section_types,
        "keyword_hits": keyword_hits,
        "hit_count": len(preview.hits or []),
        "hit_references": _hit_references(list(preview.hits or [])),
        "metric_count": len(preview.metrics or []),
        "graph_path_count": len(graph_paths),
        "warnings": list(preview.warnings or []),
        "ranking": ranking,
        "failure_categories": failure_categories,
        "answer_preview": (preview.answer or "")[:400],
        "passed": passed,
    }
