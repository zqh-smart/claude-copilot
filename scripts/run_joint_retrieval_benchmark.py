"""Joint parse/retrieval benchmark: ranking@10, abstention, true channel ablation.

Does not replace the L3 18/18 gate (`retrieval_cases`). Loads those plus optional
`benchmark_cases` from golden files listed in the joint manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_MANIFEST = (
    ROOT / "data" / "golden" / "joint_retrieval_benchmark" / "manifest.json"
)
OUT_DIR = ROOT / "data" / "reports" / "joint_retrieval_benchmark"

from scripts.retrieval_eval_common import (  # noqa: E402
    CHANNEL_ABLATION_SETS,
    load_retrieval_eval_cases,
    resolve_doc_id_from_expectations,
    score_retrieval_case,
    summarize_channel_ablation,
    summarize_retrieval_cases,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Joint retrieval benchmark runner")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--include-benchmark",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include golden benchmark_cases (default: true).",
    )
    parser.add_argument(
        "--ablation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run true channel ablation with routes_override (default: true).",
    )
    parser.add_argument(
        "--sample",
        nargs="*",
        default=None,
        help="Optional sample names from manifest (e.g. znz_2021).",
    )
    parser.add_argument(
        "--case-ids",
        nargs="*",
        default=None,
        help="Optional subset of case ids.",
    )
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Freeze the written report as baseline_joint_retrieval_benchmark.json.",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Diff latest metrics against the frozen baseline; exit 1 on gate/soft regressions.",
    )
    return parser.parse_args()


BASELINE_PATH = OUT_DIR / "baseline_joint_retrieval_benchmark.json"
DIFF_PATH = OUT_DIR / "diff_vs_baseline.json"


def _metric_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    ranking = ((report.get("diagnostics") or {}).get("ranking")) or {}
    abstention = ((report.get("diagnostics") or {}).get("abstention")) or {}
    aggregate = report.get("aggregate") or {}
    return {
        "aggregate": {
            "total": aggregate.get("total"),
            "passed": aggregate.get("passed"),
            "pass_rate": aggregate.get("pass_rate"),
            "gate_total": aggregate.get("gate_total"),
            "gate_passed": aggregate.get("gate_passed"),
            "benchmark_total": aggregate.get("benchmark_total"),
            "benchmark_passed": aggregate.get("benchmark_passed"),
        },
        "ranking": {
            "hit_rate_at_5": ranking.get("hit_rate_at_5"),
            "recall_at_5": ranking.get("recall_at_5"),
            "mrr_at_10": ranking.get("mrr_at_10"),
            "ndcg_at_10": ranking.get("ndcg_at_10"),
            "hard_negative_rate_at_5": ranking.get("hard_negative_rate_at_5"),
            "explicit_relevance_cases": ranking.get("explicit_relevance_cases"),
        },
        "abstention": {
            "evaluated_cases": abstention.get("evaluated_cases"),
            "accuracy": abstention.get("accuracy"),
        },
    }


def _compare_to_baseline(
    *, current: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    cur = _metric_snapshot(current)
    base = _metric_snapshot(baseline)
    regressions: list[str] = []
    notes: list[str] = []

    cur_gate = cur["aggregate"]["gate_passed"]
    base_gate = base["aggregate"]["gate_passed"]
    cur_gate_total = cur["aggregate"]["gate_total"]
    base_gate_total = base["aggregate"]["gate_total"]
    if cur_gate_total != base_gate_total:
        notes.append(f"gate_total changed {base_gate_total} -> {cur_gate_total}")
    if (cur_gate or 0) < (base_gate or 0):
        regressions.append(f"gate_passed {base_gate} -> {cur_gate}")

    # Soft ranking: do not require green vs targets; only flag clear regressions vs freeze.
    for key, lower_is_better in (
        ("recall_at_5", False),
        ("mrr_at_10", False),
        ("ndcg_at_10", False),
        ("hard_negative_rate_at_5", True),
    ):
        left = cur["ranking"].get(key)
        right = base["ranking"].get(key)
        if left is None or right is None:
            continue
        if lower_is_better:
            if float(left) > float(right) + 0.05:
                regressions.append(f"{key} worsened {right} -> {left}")
        elif float(left) + 0.02 < float(right):
            regressions.append(f"{key} worsened {right} -> {left}")

    cur_abs = cur["abstention"].get("accuracy")
    base_abs = base["abstention"].get("accuracy")
    if cur_abs is not None and base_abs is not None and float(cur_abs) + 1e-9 < float(base_abs):
        regressions.append(f"abstention.accuracy {base_abs} -> {cur_abs}")

    verdict = "negative" if regressions else "non_negative"
    return {
        "net_verdict": verdict,
        "regressions": regressions,
        "notes": notes,
        "current": cur,
        "baseline": base,
    }


def _preview_from_orchestrator(
    *,
    orchestrator: Any,
    doc_id: str,
    company_id: str | None,
    question: str,
    top_k: int,
    routes_override: list[str] | None = None,
    company_name: str | None = None,
    company_aliases: list[str] | None = None,
) -> SimpleNamespace:
    result = orchestrator.retrieve(
        question,
        doc_id=doc_id,
        company_id=company_id,
        top_k=top_k,
        routes_override=routes_override,
        company_name=company_name,
        company_aliases=company_aliases,
    )
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


def _build_synthetic_orchestrator(expectations: dict[str, Any]) -> tuple[Any, str]:
    """Lexical-only orchestrator backed by fixture segments (announcement / research slots)."""
    import tempfile

    from app.core.db import LocalSegmentRepository
    from app.core.rag.orchestrator import QueryAnalyzer, RetrievalOrchestrator
    from app.core.rag.retriever import LocalRetriever
    from src.claude_copilot.schemas.document import DocumentSegment

    fixture_rel = expectations.get("segments_fixture")
    if not fixture_rel:
        raise ValueError("synthetic_segments mode requires segments_fixture")
    fixture = json.loads((ROOT / fixture_rel).read_text(encoding="utf-8"))
    doc_id = str(fixture.get("doc_id") or expectations.get("document_key"))
    segments = [
        DocumentSegment(
            segment_id=str(item["segment_id"]),
            document_id=doc_id,
            position=index,
            content=str(item["content"]),
            metadata=dict(item.get("metadata") or {}),
        )
        for index, item in enumerate(fixture.get("segments") or [], start=1)
    ]
    tmp = tempfile.mkdtemp(prefix="joint_synth_")
    repo = LocalSegmentRepository(tmp)
    repo.replace_for_document(doc_id, segments)
    retriever = LocalRetriever(repo, vector_store=None)
    orchestrator = RetrievalOrchestrator(
        vector_retriever=retriever,
        financial_repository=_NullFinancialRepo(),
        graph_store=None,
        query_analyzer=QueryAnalyzer(),
    )
    return orchestrator, doc_id


class _NullFinancialRepo:
    def list_companies(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    def get_company(self, *args: Any, **kwargs: Any) -> None:
        return None

    def query_metrics(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


def _run_sample(
    *,
    sample: dict[str, Any],
    include_benchmark: bool,
    case_ids: list[str] | None,
    top_k: int,
    run_ablation: bool,
) -> dict[str, Any]:
    from app.api import dependencies
    from app.core.config import get_settings
    from app.core.db import build_company_id
    from app.core.rag.orchestrator import RetrievalOrchestrator
    from app.core.rag.retriever import LocalRetriever

    golden_path = ROOT / sample["golden"]
    expectations = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = load_retrieval_eval_cases(
        expectations,
        include_benchmark=include_benchmark,
        case_ids=case_ids,
    )
    if not cases:
        raise ValueError(f"No cases for sample {sample['name']} in {golden_path}")

    synthetic = (
        expectations.get("mode") == "synthetic_segments"
        or sample.get("status") == "synthetic_ready"
    )
    company_name: str | None = None
    company_aliases: list[str] = []
    if synthetic:
        orchestrator, doc_id = _build_synthetic_orchestrator(expectations)
        company_id = None
        company_name = expectations.get("company") or expectations.get("company_name")
        company_aliases = list(expectations.get("company_aliases") or [])
    else:
        doc_id = resolve_doc_id_from_expectations(doc_id=None, expectations=expectations)
        record = dependencies.get_document_pipeline_service().get_document(doc_id)
        company_id = (
            build_company_id(record.metadata.company) if record.metadata.company else None
        )
        company_name = record.metadata.company
        company_aliases = list(record.metadata.company_aliases or [])
        settings = get_settings()
        retriever = LocalRetriever(
            dependencies.get_segment_repository(),
            vector_store=dependencies.get_vector_store(),
            reranker=dependencies.get_reranking_service(),
            candidate_multiplier=settings.retrieval_candidate_multiplier,
            vector_weight=settings.hybrid_vector_weight,
            lexical_weight=settings.hybrid_lexical_weight,
        )
        orchestrator = RetrievalOrchestrator(
            vector_retriever=retriever,
            financial_repository=dependencies.get_financial_data_repository(),
            graph_store=dependencies.get_graph_store(),
        )

    case_results: list[dict[str, Any]] = []
    ablation_rows: list[dict[str, Any]] = []
    # Synthetic fixtures have no SQL/graph backends; force vector so semantic labels score.
    default_routes = ["vector"] if synthetic else None
    for case in cases:
        t0 = time.perf_counter()
        preview = _preview_from_orchestrator(
            orchestrator=orchestrator,
            doc_id=doc_id,
            company_id=company_id,
            question=case["question"],
            top_k=top_k,
            routes_override=default_routes,
            company_name=company_name,
            company_aliases=company_aliases,
        )
        scored = score_retrieval_case(case, preview)
        scored["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        scored["sample"] = sample["name"]
        benchmark_ids = {
            str(item.get("id")) for item in (expectations.get("benchmark_cases") or [])
        }
        scored["suite"] = "benchmark" if str(case.get("id")) in benchmark_ids else "gate"
        case_results.append(scored)
        print(json.dumps(scored, ensure_ascii=False, indent=2))

        if run_ablation:
            for channel, routes in CHANNEL_ABLATION_SETS.items():
                abl_preview = _preview_from_orchestrator(
                    orchestrator=orchestrator,
                    doc_id=doc_id,
                    company_id=company_id,
                    question=case["question"],
                    top_k=top_k,
                    routes_override=routes,
                    company_name=company_name,
                    company_aliases=company_aliases,
                )
                abl_scored = score_retrieval_case(case, abl_preview)
                ablation_rows.append(
                    {
                        "sample": sample["name"],
                        "case_id": case.get("id"),
                        "channel": channel,
                        "routes": routes,
                        "passed": abl_scored["passed"],
                        "failure_categories": abl_scored["failure_categories"],
                        "hit_count": abl_scored["hit_count"],
                        "metric_count": abl_scored["metric_count"],
                        "graph_path_count": abl_scored["graph_path_count"],
                    }
                )

    passed = sum(1 for item in case_results if item["passed"])
    return {
        "sample": sample["name"],
        "role": sample.get("role"),
        "status": sample.get("status"),
        "doc_id": doc_id,
        "document_key": expectations.get("document_key"),
        "expectations": str(golden_path),
        "total": len(case_results),
        "passed": passed,
        "pass_rate": round(passed / max(len(case_results), 1), 4),
        "diagnostics": summarize_retrieval_cases(case_results),
        "channel_ablation": summarize_channel_ablation(ablation_rows) if ablation_rows else {},
        "cases": case_results,
        "ablation_rows": ablation_rows,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    samples = list(manifest.get("samples") or [])
    if args.sample:
        allowed = set(args.sample)
        samples = [item for item in samples if item.get("name") in allowed]
    # ready = Serving-backed; synthetic_ready = fixture segments; draft = planning only.
    runnable = [
        item
        for item in samples
        if item.get("status") in {"ready", "synthetic_ready"} and item.get("golden")
    ]
    if not runnable:
        raise ValueError("No ready/synthetic_ready samples in manifest.")

    from app.api import dependencies
    from app.core.config import get_settings

    needs_services = any(item.get("status") == "ready" for item in runnable)
    if needs_services:
        get_settings.cache_clear()
        for name in dir(dependencies):
            obj = getattr(dependencies, name)
            if callable(obj) and hasattr(obj, "cache_clear"):
                obj.cache_clear()

    sample_reports = [
        _run_sample(
            sample=sample,
            include_benchmark=args.include_benchmark,
            case_ids=args.case_ids,
            top_k=args.top_k,
            run_ablation=args.ablation and sample.get("status") == "ready",
        )
        for sample in runnable
    ]

    all_cases = [case for report in sample_reports for case in report["cases"]]
    all_ablation = [
        row for report in sample_reports for row in report.get("ablation_rows") or []
    ]
    aggregate = {
        "total": len(all_cases),
        "passed": sum(1 for case in all_cases if case["passed"]),
        "pass_rate": round(
            sum(1 for case in all_cases if case["passed"]) / max(len(all_cases), 1),
            4,
        ),
        "gate_total": sum(1 for case in all_cases if case.get("suite") == "gate"),
        "gate_passed": sum(
            1 for case in all_cases if case.get("suite") == "gate" and case["passed"]
        ),
        "benchmark_total": sum(1 for case in all_cases if case.get("suite") == "benchmark"),
        "benchmark_passed": sum(
            1
            for case in all_cases
            if case.get("suite") == "benchmark" and case["passed"]
        ),
    }
    report = {
        "manifest": str(args.manifest),
        "thresholds": manifest.get("thresholds") or {},
        "top_k": args.top_k,
        "include_benchmark": args.include_benchmark,
        "ablation": args.ablation,
        "aggregate": aggregate,
        "diagnostics": summarize_retrieval_cases(all_cases),
        "channel_ablation": summarize_channel_ablation(all_ablation) if all_ablation else {},
        "samples": [
            {
                "name": item["sample"],
                "role": item.get("role"),
                "doc_id": item.get("doc_id"),
                "pass_rate": item.get("pass_rate"),
                "total": item.get("total"),
                "passed": item.get("passed"),
                "diagnostics": item.get("diagnostics"),
                "channel_ablation": item.get("channel_ablation"),
            }
            for item in sample_reports
        ],
        "case_results": all_cases,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "latest_joint_retrieval_benchmark.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "wrote": str(out_path),
        "aggregate": aggregate,
        "ranking": report["diagnostics"].get("ranking"),
        "channel_ablation": report["channel_ablation"],
    }

    if args.save_baseline:
        frozen = dict(report)
        frozen["baseline_meta"] = {
            "frozen_at": datetime.now(UTC).isoformat(),
            "policy": (
                "Corpus freeze for current documents. Do not expand questions or tune "
                "fusion weights unless chasing soft-target green or production ranking bugs; "
                "then prefer query-aware / section ownership."
            ),
            "corpus": {
                "documents": len(runnable),
                "questions": aggregate["total"],
                "gate": aggregate["gate_total"],
                "benchmark": aggregate["benchmark_total"],
            },
        }
        BASELINE_PATH.write_text(
            json.dumps(frozen, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary["saved_baseline"] = str(BASELINE_PATH)

    if args.compare_baseline:
        if not BASELINE_PATH.exists():
            print("NO_BASELINE: run with --save-baseline first")
            return 2
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        diff = _compare_to_baseline(current=report, baseline=baseline)
        DIFF_PATH.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["diff_vs_baseline"] = diff
        summary["wrote_diff"] = str(DIFF_PATH)

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Soft exit: gate regressions hard-fail; benchmark expansion may be red while labelling.
    gate_ok = aggregate["gate_passed"] == aggregate["gate_total"]
    if not gate_ok:
        return 2
    if args.compare_baseline and summary.get("diff_vs_baseline", {}).get("net_verdict") == "negative":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
