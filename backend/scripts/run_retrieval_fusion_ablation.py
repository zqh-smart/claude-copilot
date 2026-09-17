"""Compare hybrid fusion modes (linear vs RRF) on L3 retrieval cases."""

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

OUT_DIR = ROOT / "data" / "reports" / "retrieval_fusion_ablation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hybrid fusion ablation (linear vs rrf)")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--golden",
        type=Path,
        default=ROOT / "data" / "golden" / "retrieval_cases.json",
    )
    return parser.parse_args()


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
    )


def _run_mode(mode: str, *, top_k: int, golden: Path) -> dict:
    from app.api import dependencies
    from app.core.config import get_settings
    from scripts.retrieval_eval_common import (
        load_retrieval_eval_cases,
        score_retrieval_case,
        summarize_retrieval_cases,
    )

    os.environ["HYBRID_FUSION_MODE"] = mode
    get_settings.cache_clear()
    dependencies.get_research_service.cache_clear()

    orchestrator = dependencies.get_research_service().orchestrator
    if orchestrator is None:
        raise RuntimeError("Retrieval orchestrator is not configured.")

    cases = load_retrieval_eval_cases(golden)
    scored = []
    for case in cases:
        doc_id = case.get("doc_id")
        if not doc_id:
            continue
        preview = _preview_from_orchestrator(
            orchestrator,
            doc_id=doc_id,
            question=case["question"],
            top_k=top_k,
        )
        scored.append(score_retrieval_case(case, preview))
    summary = summarize_retrieval_cases(scored)
    return {"fusion_mode": mode, "case_count": len(scored), "summary": summary}


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "top_k": args.top_k,
        "golden": str(args.golden),
        "modes": [
            _run_mode("linear", top_k=args.top_k, golden=args.golden),
            _run_mode("rrf", top_k=args.top_k, golden=args.golden),
        ],
    }
    out_path = OUT_DIR / "latest_fusion_ablation.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
