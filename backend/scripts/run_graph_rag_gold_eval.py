"""Run expanded GraphRAG gold queries against the live orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "data" / "reports" / "graph_rag_gold"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GraphRAG gold eval (100+ expanded cases)")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "data" / "fixtures" / "graph_rag_gold_queries.json",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=0,
        help="Optional cap (0 = all expanded cases).",
    )
    parser.add_argument(
        "--sample-slots",
        nargs="*",
        default=None,
        help="Filter doc_slots by slot id (e.g. znz jucan).",
    )
    return parser.parse_args()


def _normalize_case(case: dict) -> dict:
    normalized = dict(case)
    if normalized.get("expect_route"):
        return normalized
    routes = [str(item).casefold() for item in (normalized.get("expect_routes") or [])]
    if "hybrid" in routes:
        normalized["expect_route"] = "hybrid"
    elif "relational" in routes:
        normalized["expect_route"] = "relational"
    elif "graph" in routes:
        normalized["expect_route"] = "graph"
    elif "sql" in routes and "vector" not in routes:
        normalized["expect_route"] = "structured"
    elif "vector" in routes:
        normalized["expect_route"] = "semantic"
    return normalized


def _preview_from_orchestrator(orchestrator, *, doc_id: str, question: str, top_k: int):
    result = orchestrator.retrieve(question, doc_id=doc_id, top_k=top_k)
    hits = [
        SimpleNamespace(
            segment_id=segment.segment_id,
            score=round(score, 4),
            content=segment.content,
            metadata=dict(segment.metadata or {}),
        )
        for segment, score in result.vector_hits
    ]
    return SimpleNamespace(
        query_analysis=result.analysis,
        hits=hits,
        metrics=result.metrics,
        graph_paths=result.graph_paths,
        warnings=list(result.warnings or []),
        answer="",
    )


def main() -> int:
    from app.api import dependencies
    from app.core.rag.graph_rag_gold import expand_graph_rag_cases, load_graph_rag_gold_fixture
    from scripts.retrieval_eval_common import resolve_doc_id_from_expectations, score_retrieval_case

    args = parse_args()
    fixture = load_graph_rag_gold_fixture(args.fixture)
    cases = expand_graph_rag_cases(fixture)
    if args.sample_slots:
        allowed = set(args.sample_slots)
        cases = [case for case in cases if any(tag in allowed for tag in case.get("tags") or [])]
    if args.max_cases > 0:
        cases = cases[: args.max_cases]

    try:
        orchestrator = dependencies.get_research_service().orchestrator
    except Exception as exc:  # noqa: BLE001
        from app.core.errors import PersistenceBackendError

        if isinstance(exc, PersistenceBackendError) or "ConnectionTimeout" in type(exc).__name__:
            print(
                "GraphRAG gold eval requires a reachable storage backend "
                "(Postgres when STORAGE_BACKEND=postgres). Start docker compose or "
                "use local JSON storage before running this script.",
                file=sys.stderr,
            )
            return 4
        raise
    if orchestrator is None:
        print("Orchestrator unavailable.", file=sys.stderr)
        return 2

    scored: list[dict] = []
    skipped: list[str] = []
    for case in cases:
        expectations = {"document_key": case.get("document_key")}
        try:
            doc_id = resolve_doc_id_from_expectations(doc_id=None, expectations=expectations)
        except FileNotFoundError:
            skipped.append(str(case.get("id")))
            continue
        preview = _preview_from_orchestrator(
            orchestrator,
            doc_id=doc_id,
            question=str(case["question"]),
            top_k=args.top_k,
        )
        row = score_retrieval_case(_normalize_case(case), preview)
        row["document_key"] = case.get("document_key")
        scored.append(row)

    passed = sum(1 for row in scored if row.get("passed"))
    graph_ok = sum(1 for row in scored if row.get("graph_ok"))
    report = {
        "fixture": str(args.fixture),
        "expanded_case_count": len(cases),
        "executed_case_count": len(scored),
        "skipped_case_count": len(skipped),
        "pass_rate": round(passed / max(len(scored), 1), 4),
        "graph_ok_rate": round(graph_ok / max(len(scored), 1), 4),
        "skipped_ids_sample": skipped[:20],
        "cases": scored,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "latest_graph_rag_gold.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False, indent=2))
    return 0 if scored else 1


if __name__ == "__main__":
    raise SystemExit(main())
