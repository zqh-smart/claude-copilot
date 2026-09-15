"""Compare research retrieval with agentic second pass on vs off."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "data" / "reports" / "agentic_retrieval_ablation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agentic second-pass ablation")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--golden",
        type=Path,
        default=ROOT / "data" / "golden" / "retrieval_cases.json",
    )
    return parser.parse_args()


def _preview_from_run(result: dict) -> SimpleNamespace:
    from src.claude_copilot.schemas.research import QueryAnalysis

    qa = (
        QueryAnalysis.model_validate(result["query_analysis"])
        if result.get("query_analysis")
        else None
    )
    hits = [
        SimpleNamespace(
            segment_id=item.get("segment_id"),
            score=item.get("score"),
            content=item.get("content") or "",
            metadata=dict(item.get("metadata") or {}),
        )
        for item in result.get("hits") or []
    ]
    return SimpleNamespace(
        query_analysis=qa,
        hits=hits,
        metrics=result.get("metrics") or [],
        graph_paths=result.get("graph_paths") or [],
        warnings=list(result.get("warnings") or []),
    )


def _run_variant(*, agentic_enabled: bool, top_k: int, golden: Path) -> dict:
    from app.api import dependencies
    from app.core.config import get_settings
    from scripts.retrieval_eval_common import (
        load_retrieval_eval_cases,
        score_retrieval_case,
        summarize_retrieval_cases,
    )

    os.environ["RESEARCH_AGENTIC_SECOND_PASS_ENABLED"] = (
        "true" if agentic_enabled else "false"
    )
    os.environ["RESEARCH_DEEP_RETRIEVAL_ENABLED"] = "false"
    get_settings.cache_clear()
    dependencies.get_research_service.cache_clear()

    service = dependencies.get_research_service()
    cases = load_retrieval_eval_cases(golden)
    scored = []
    second_passes = 0
    for case in cases:
        doc_id = case.get("doc_id")
        if not doc_id:
            continue
        run = service._run_retrieval(
            {"doc_id": doc_id, "question": case["question"], "top_k": top_k}
        )
        if int(run.get("retrieval_passes") or 1) >= 2:
            second_passes += 1
        scored.append(score_retrieval_case(case, _preview_from_run(run)))
    summary = summarize_retrieval_cases(scored)
    return {
        "agentic_second_pass_enabled": agentic_enabled,
        "case_count": len(scored),
        "second_pass_rate": round(second_passes / max(len(scored), 1), 4),
        "summary": summary,
    }


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "top_k": args.top_k,
        "golden": str(args.golden),
        "variants": [
            _run_variant(agentic_enabled=False, top_k=args.top_k, golden=args.golden),
            _run_variant(agentic_enabled=True, top_k=args.top_k, golden=args.golden),
        ],
    }
    out_path = OUT_DIR / "latest_agentic_ablation.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
