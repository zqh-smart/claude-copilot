"""L4 batch eval: grounded research + critic over golden retrieval cases."""

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

DEFAULT_GOLDEN = ROOT / "data" / "golden" / "znz_2021_stage_expectations.json"
OUT_DIR = ROOT / "data" / "reports" / "l4_eval"

from scripts.retrieval_eval_common import (  # noqa: E402
    resolve_doc_id_from_expectations,
    score_retrieval_case,
    values_equal,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="L4 grounded research + critic eval")
    parser.add_argument("--expectations", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument(
        "--doc-id",
        default=None,
        help="Completed document id (default: resolve from serving eval report or metadata).",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--case-ids",
        nargs="*",
        default=None,
        help="Optional subset of case ids to run.",
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Skip LLM probe; score evidence + structured value match only (L4 offline baseline).",
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


def _probe_llm() -> dict:
    from app.core.config import get_settings
    from app.core.llm.client import build_json_chat_client

    settings = get_settings()
    info: dict = {
        "api_type": settings.llm_model_api_type,
        "model": settings.llm_model_name,
        "base_url": settings.llm_model_base_url,
        "grounded_synthesis_enabled": settings.llm_grounded_synthesis_enabled,
        "ok": False,
    }
    try:
        client = build_json_chat_client(settings)
        payload = client.complete_json(
            system_prompt='Return JSON exactly: {"status":"ok"}',
            user_prompt="ping",
        )
        info["ok"] = payload.get("status") == "ok"
        if not info["ok"]:
            info["error"] = f"Unexpected probe payload: {payload!r}"
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def _value_in_text(value, text: str) -> bool:
    if not text:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value).strip() in text

    normalized = text.replace(",", "").replace("，", "")
    if str(int(number)) in normalized:
        return True
    compact = f"{number:.2f}".rstrip("0").rstrip(".")
    return compact in normalized or f"{number:.4f}".rstrip("0").rstrip(".") in normalized


def _load_cases(expectations: dict, case_ids: list[str] | None) -> list[dict]:
    cases = expectations.get("l4_cases") or expectations.get("retrieval_cases") or []
    if case_ids:
        allowed = set(case_ids)
        cases = [case for case in cases if case.get("id") in allowed]
    return cases


def _has_evidence(preview) -> bool:
    return bool(preview.hits or preview.metrics or preview.graph_paths)


def _expect_value_ok(case: dict, preview) -> bool | None:
    expected = case.get("expect_value")
    if expected is None:
        return None

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
        if case.get("expect_metric_key") and key != case["expect_metric_key"]:
            continue
        if case.get("expect_period") and str(period) != str(case["expect_period"]):
            continue
        if values_equal(value, expected):
            return True

    answer = preview.answer or ""
    synthesis_answer = preview.synthesis.answer if preview.synthesis else ""
    blob = "\n".join(part for part in (answer, synthesis_answer) if part)
    return _value_in_text(expected, blob)


def _score_case(case: dict, preview) -> dict:
    synthesis = preview.synthesis
    critic = preview.critic
    citations = list(synthesis.citations) if synthesis else []
    has_citations = bool(citations)
    critic_passed = bool(critic.passed) if critic else False
    grounded = bool(preview.grounded)
    evidence_present = _has_evidence(preview)
    value_ok = _expect_value_ok(case, preview)

    citations_ok = has_citations if evidence_present else True
    value_check_ok = value_ok if value_ok is not None else True
    passed = bool(grounded and critic_passed and citations_ok and value_check_ok)

    return {
        "id": case.get("id"),
        "question": case.get("question"),
        "grounded": grounded,
        "critic_passed": critic_passed,
        "has_citations": has_citations,
        "citations_count": len(citations),
        "expect_value_ok": value_ok,
        "evidence_present": evidence_present,
        "revision_count": preview.revision_count,
        "critic_summary": critic.summary if critic else None,
        "critic_issue_count": len(critic.issues) if critic else 0,
        "warnings": list(preview.warnings or []),
        "answer_preview": (preview.answer or "")[:400],
        "passed": passed,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    expectations = json.loads(args.expectations.read_text(encoding="utf-8"))
    cases = _load_cases(expectations, args.case_ids)
    if not cases:
        raise ValueError("No L4 cases found in expectations (l4_cases / retrieval_cases).")

    if args.retrieval_only:
        os.environ["LLM_GROUNDED_SYNTHESIS_ENABLED"] = "false"
    else:
        os.environ["LLM_GROUNDED_SYNTHESIS_ENABLED"] = "true"
    _reset_caches()

    if args.retrieval_only:
        from app.api import dependencies
        from app.core.config import get_settings

        settings = get_settings()
        doc_id = resolve_doc_id_from_expectations(doc_id=args.doc_id, expectations=expectations)
        research = dependencies.get_research_service()
        case_results = []
        t0 = time.perf_counter()
        for case in cases:
            preview = research.preview(doc_id=doc_id, question=case["question"], top_k=args.top_k)
            scored = score_retrieval_case(case, preview)
            case_results.append(scored)
            print(json.dumps(scored, ensure_ascii=False, indent=2))

        elapsed = round(time.perf_counter() - t0, 3)
        passed = sum(1 for item in case_results if item["passed"])
        report = {
            "mode": "retrieval_only",
            "doc_id": doc_id,
            "document_key": expectations.get("document_key"),
            "expectations": str(args.expectations),
            "elapsed_seconds": elapsed,
            "backends": {
                "storage": settings.storage_backend,
                "vector": settings.vector_store_backend,
                "graph": settings.graph_store_backend,
                "embedding": settings.embedding_backend,
            },
            "l4_retrieval": {
                "total": len(case_results),
                "passed": passed,
                "pass_rate": round(passed / max(len(case_results), 1), 4),
                "cases": case_results,
            },
        }
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUT_DIR / f"{doc_id}_l4_retrieval_eval.json"
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "wrote": str(out_path),
                    "l4_retrieval_pass_rate": report["l4_retrieval"]["pass_rate"],
                    "elapsed_seconds": elapsed,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if case_results and passed < len(case_results):
            return 2
        return 0

    llm_info = _probe_llm()
    print(json.dumps({"llm_probe": llm_info}, ensure_ascii=False, indent=2))
    if not llm_info.get("ok"):
        message = (
            "LLM unavailable for L4 eval. "
            "Check LLM_MODEL_* / SILICON_KEY and that chat endpoint responds. "
            f"Details: {llm_info.get('error', 'probe failed')}"
        )
        print(message, file=sys.stderr)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUT_DIR / "llm_unavailable.json"
        out_path.write_text(
            json.dumps(
                {
                    "status": "llm_unavailable",
                    "message": message,
                    "llm_probe": llm_info,
                    "expectations": str(args.expectations),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(json.dumps({"wrote": str(out_path)}, ensure_ascii=False))
        return 4

    from app.api import dependencies
    from app.core.config import get_settings

    settings = get_settings()
    if settings.llm_grounded_synthesis_enabled is not True:
        print("LLM_GROUNDED_SYNTHESIS_ENABLED is false after reset.", file=sys.stderr)
        return 4

    doc_id = resolve_doc_id_from_expectations(doc_id=args.doc_id, expectations=expectations)
    research = dependencies.get_research_service()
    if dependencies.get_grounded_research_engine() is None:
        print("Grounded research engine not configured.", file=sys.stderr)
        return 4

    case_results = []
    t0 = time.perf_counter()
    for case in cases:
        preview = research.preview(doc_id=doc_id, question=case["question"], top_k=args.top_k)
        scored = _score_case(case, preview)
        case_results.append(scored)
        print(json.dumps(scored, ensure_ascii=False, indent=2))

    elapsed = round(time.perf_counter() - t0, 3)
    passed = sum(1 for item in case_results if item["passed"])
    report = {
        "doc_id": doc_id,
        "document_key": expectations.get("document_key"),
        "expectations": str(args.expectations),
        "elapsed_seconds": elapsed,
        "llm_probe": llm_info,
        "backends": {
            "storage": settings.storage_backend,
            "vector": settings.vector_store_backend,
            "graph": settings.graph_store_backend,
            "embedding": settings.embedding_backend,
        },
        "l4": {
            "total": len(case_results),
            "passed": passed,
            "pass_rate": round(passed / max(len(case_results), 1), 4),
            "grounded_rate": round(
                sum(1 for item in case_results if item["grounded"]) / max(len(case_results), 1),
                4,
            ),
            "critic_pass_rate": round(
                sum(1 for item in case_results if item["critic_passed"]) / max(len(case_results), 1),
                4,
            ),
            "cases": case_results,
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{doc_id}_l4_eval.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(out_path),
                "l4_pass_rate": report["l4"]["pass_rate"],
                "elapsed_seconds": elapsed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if case_results and passed < len(case_results):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
