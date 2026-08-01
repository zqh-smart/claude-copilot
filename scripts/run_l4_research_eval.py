"""L4 batch eval: grounded research + critic over golden retrieval cases."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLDEN_DIR = ROOT / "data" / "golden"
DEFAULT_GOLDEN = GOLDEN_DIR / "znz_2021_stage_expectations.json"
OUT_DIR = ROOT / "data" / "reports" / "l4_eval"

# Documented soft/hard gates (see docs/acceptance_suite.md § L4).
L4_THRESHOLDS = {
    "smoke_full_pass_rate": 1.0,  # znz full L4 when LLM available — do not regress
    "retrieval_only_pass_rate": 1.0,  # all samples before claiming L4-ready evidence
    "regression_full_min_pass_rate": 0.8,  # jucan/tianhua stretch; report, not hard CI
}

L4_SAMPLE_CATALOG: list[dict[str, Any]] = [
    {
        "name": "znz_2021",
        "role": "smoke",
        "golden": GOLDEN_DIR / "znz_2021_stage_expectations.json",
    },
    {
        "name": "jucan_2021",
        "role": "regression",
        "golden": GOLDEN_DIR / "jucan_2021_stage_expectations.json",
    },
    {
        "name": "tianhua_2021",
        "role": "regression",
        "golden": GOLDEN_DIR / "tianhua_2021_stage_expectations.json",
    },
]

from scripts.retrieval_eval_common import (  # noqa: E402
    resolve_doc_id_from_expectations,
    score_retrieval_case,
    values_equal,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="L4 grounded research + critic eval")
    parser.add_argument(
        "--expectations",
        type=Path,
        default=None,
        help="Single golden JSON (default: znz when --profile omitted).",
    )
    parser.add_argument(
        "--profile",
        choices=("smoke", "regression", "all"),
        default=None,
        help="Multi-sample profile: smoke=znz; regression=jucan+tianhua; all=three.",
    )
    parser.add_argument(
        "--doc-id",
        default=None,
        help="Completed document id (single-sample only; default: resolve from serving eval).",
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


def resolve_l4_samples(
    *,
    profile: str | None,
    expectations: Path | None,
) -> list[dict[str, Any]]:
    """Resolve one or more golden samples for L4 eval."""
    if profile == "smoke":
        return [dict(item) for item in L4_SAMPLE_CATALOG if item["role"] == "smoke"]
    if profile == "regression":
        return [dict(item) for item in L4_SAMPLE_CATALOG if item["role"] == "regression"]
    if profile == "all":
        return [dict(item) for item in L4_SAMPLE_CATALOG]
    path = expectations or DEFAULT_GOLDEN
    return [
        {
            "name": path.stem.replace("_stage_expectations", ""),
            "role": "custom",
            "golden": path,
        }
    ]


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


def _gate_status(sample: dict[str, Any], pass_rate: float, *, retrieval_only: bool) -> dict[str, Any]:
    role = sample.get("role")
    if retrieval_only:
        threshold = L4_THRESHOLDS["retrieval_only_pass_rate"]
        return {
            "threshold": threshold,
            "met": pass_rate >= threshold,
            "kind": "retrieval_only",
        }
    if role == "smoke":
        threshold = L4_THRESHOLDS["smoke_full_pass_rate"]
        return {
            "threshold": threshold,
            "met": pass_rate >= threshold,
            "kind": "smoke_full",
        }
    if role == "regression":
        threshold = L4_THRESHOLDS["regression_full_min_pass_rate"]
        return {
            "threshold": threshold,
            "met": pass_rate >= threshold,
            "kind": "regression_full_soft",
        }
    return {
        "threshold": L4_THRESHOLDS["smoke_full_pass_rate"],
        "met": pass_rate >= L4_THRESHOLDS["smoke_full_pass_rate"],
        "kind": "custom_full",
    }


def _run_retrieval_sample(
    *,
    sample: dict[str, Any],
    doc_id_override: str | None,
    top_k: int,
    case_ids: list[str] | None,
) -> dict[str, Any]:
    from app.api import dependencies
    from app.core.config import get_settings

    golden_path: Path = sample["golden"]
    expectations = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = _load_cases(expectations, case_ids)
    if not cases:
        raise ValueError(f"No L4 cases in {golden_path}")

    settings = get_settings()
    doc_id = resolve_doc_id_from_expectations(
        doc_id=doc_id_override,
        expectations=expectations,
    )
    research = dependencies.get_research_service()
    case_results = []
    t0 = time.perf_counter()
    for case in cases:
        preview = research.preview(doc_id=doc_id, question=case["question"], top_k=top_k)
        scored = score_retrieval_case(case, preview)
        case_results.append(scored)
        print(json.dumps({"sample": sample["name"], **scored}, ensure_ascii=False, indent=2))

    elapsed = round(time.perf_counter() - t0, 3)
    passed = sum(1 for item in case_results if item["passed"])
    pass_rate = round(passed / max(len(case_results), 1), 4)
    report = {
        "mode": "retrieval_only",
        "sample": sample["name"],
        "role": sample.get("role"),
        "doc_id": doc_id,
        "document_key": expectations.get("document_key"),
        "expectations": str(golden_path),
        "elapsed_seconds": elapsed,
        "backends": {
            "storage": settings.storage_backend,
            "vector": settings.vector_store_backend,
            "graph": settings.graph_store_backend,
            "embedding": settings.embedding_backend,
        },
        "gate": _gate_status(sample, pass_rate, retrieval_only=True),
        "l4_retrieval": {
            "total": len(case_results),
            "passed": passed,
            "pass_rate": pass_rate,
            "cases": case_results,
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{doc_id}_l4_retrieval_eval.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["wrote"] = str(out_path)
    return report


def _run_full_sample(
    *,
    sample: dict[str, Any],
    doc_id_override: str | None,
    top_k: int,
    case_ids: list[str] | None,
    llm_info: dict,
) -> dict[str, Any]:
    from app.api import dependencies
    from app.core.config import get_settings

    golden_path: Path = sample["golden"]
    expectations = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = _load_cases(expectations, case_ids)
    if not cases:
        raise ValueError(f"No L4 cases in {golden_path}")

    settings = get_settings()
    doc_id = resolve_doc_id_from_expectations(
        doc_id=doc_id_override,
        expectations=expectations,
    )
    research = dependencies.get_research_service()
    case_results = []
    t0 = time.perf_counter()
    for case in cases:
        preview = research.preview(doc_id=doc_id, question=case["question"], top_k=top_k)
        scored = _score_case(case, preview)
        case_results.append(scored)
        print(json.dumps({"sample": sample["name"], **scored}, ensure_ascii=False, indent=2))

    elapsed = round(time.perf_counter() - t0, 3)
    passed = sum(1 for item in case_results if item["passed"])
    pass_rate = round(passed / max(len(case_results), 1), 4)
    report = {
        "mode": "full",
        "sample": sample["name"],
        "role": sample.get("role"),
        "doc_id": doc_id,
        "document_key": expectations.get("document_key"),
        "expectations": str(golden_path),
        "elapsed_seconds": elapsed,
        "llm_probe": llm_info,
        "backends": {
            "storage": settings.storage_backend,
            "vector": settings.vector_store_backend,
            "graph": settings.graph_store_backend,
            "embedding": settings.embedding_backend,
        },
        "gate": _gate_status(sample, pass_rate, retrieval_only=False),
        "l4": {
            "total": len(case_results),
            "passed": passed,
            "pass_rate": pass_rate,
            "grounded_rate": round(
                sum(1 for item in case_results if item["grounded"]) / max(len(case_results), 1),
                4,
            ),
            "critic_pass_rate": round(
                sum(1 for item in case_results if item["critic_passed"])
                / max(len(case_results), 1),
                4,
            ),
            "cases": case_results,
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{doc_id}_l4_eval.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["wrote"] = str(out_path)
    return report


def _write_summary(
    *,
    profile: str | None,
    mode: str,
    sample_reports: list[dict[str, Any]],
) -> Path:
    totals = 0
    passed = 0
    for report in sample_reports:
        block = report.get("l4") or report.get("l4_retrieval") or {}
        totals += int(block.get("total") or 0)
        passed += int(block.get("passed") or 0)
    summary = {
        "profile": profile or "single",
        "mode": mode,
        "thresholds": L4_THRESHOLDS,
        "samples": [
            {
                "name": item.get("sample"),
                "role": item.get("role"),
                "doc_id": item.get("doc_id"),
                "document_key": item.get("document_key"),
                "pass_rate": (item.get("l4") or item.get("l4_retrieval") or {}).get("pass_rate"),
                "gate": item.get("gate"),
                "wrote": item.get("wrote"),
                "elapsed_seconds": item.get("elapsed_seconds"),
            }
            for item in sample_reports
        ],
        "aggregate": {
            "total": totals,
            "passed": passed,
            "pass_rate": round(passed / max(totals, 1), 4),
            "all_gates_met": all(
                bool((item.get("gate") or {}).get("met")) for item in sample_reports
            ),
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "latest_l4_summary.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote_summary": str(out_path), **summary["aggregate"]}, ensure_ascii=False, indent=2))
    return out_path


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    samples = resolve_l4_samples(profile=args.profile, expectations=args.expectations)
    if args.doc_id and len(samples) > 1:
        print(
            "--doc-id applies only to single-sample runs; ignoring for multi-sample profile.",
            file=sys.stderr,
        )
        doc_id_override = None
    else:
        doc_id_override = args.doc_id

    if args.retrieval_only:
        os.environ["LLM_GROUNDED_SYNTHESIS_ENABLED"] = "false"
    else:
        os.environ["LLM_GROUNDED_SYNTHESIS_ENABLED"] = "true"
    _reset_caches()

    if args.retrieval_only:
        reports = [
            _run_retrieval_sample(
                sample=sample,
                doc_id_override=doc_id_override,
                top_k=args.top_k,
                case_ids=args.case_ids,
            )
            for sample in samples
        ]
        _write_summary(profile=args.profile, mode="retrieval_only", sample_reports=reports)
        if any(
            (item.get("l4_retrieval") or {}).get("passed", 0)
            < (item.get("l4_retrieval") or {}).get("total", 0)
            for item in reports
        ):
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
                    "profile": args.profile,
                    "samples": [item["name"] for item in samples],
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
    if dependencies.get_grounded_research_engine() is None:
        print("Grounded research engine not configured.", file=sys.stderr)
        return 4

    reports = [
        _run_full_sample(
            sample=sample,
            doc_id_override=doc_id_override,
            top_k=args.top_k,
            case_ids=args.case_ids,
            llm_info=llm_info,
        )
        for sample in samples
    ]
    _write_summary(profile=args.profile, mode="full", sample_reports=reports)

    # Exit: fail hard if smoke/custom below full threshold; regression soft gate only warns.
    hard_fail = False
    soft_warn = False
    for item in reports:
        block = item.get("l4") or {}
        rate = float(block.get("pass_rate") or 0.0)
        role = item.get("role")
        if role == "regression":
            if rate < L4_THRESHOLDS["regression_full_min_pass_rate"]:
                soft_warn = True
            if block.get("passed", 0) < block.get("total", 0):
                soft_warn = True
        else:
            if block.get("passed", 0) < block.get("total", 0):
                hard_fail = True
    if soft_warn and not hard_fail:
        print(
            json.dumps(
                {
                    "warning": "regression L4 below soft threshold or incomplete",
                    "threshold": L4_THRESHOLDS["regression_full_min_pass_rate"],
                },
                ensure_ascii=False,
            )
        )
    if hard_fail:
        return 2
    if soft_warn:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
