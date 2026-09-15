"""Patch local golden expectation files with consolidated scope truth.

Golden files live under data/golden/ and are gitignored; run after pulling truth updates:

  uv run python scripts/sync_golden_entity_scope.py
  uv run python scripts/sync_golden_entity_scope.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRUTH_PATH = ROOT / "data" / "fixtures" / "consolidated_metric_truth.json"
GOLDEN_DIR = ROOT / "data" / "golden"

SAMPLE_FILES = {
    "znz_2021": "znz_2021_stage_expectations.json",
    "jucan_2021": "jucan_2021_stage_expectations.json",
    "tianhua_2021": "tianhua_2021_stage_expectations.json",
}


def _load_truth() -> dict:
    return json.loads(TRUTH_PATH.read_text(encoding="utf-8"))


def _infer_sample(path: Path) -> str | None:
    for key, filename in SAMPLE_FILES.items():
        if path.name == filename:
            return key
    return None


def _scope_for_question(question: str, default: str) -> str:
    text = question.casefold()
    if any(cue in text for cue in ("母公司", "parent company", "standalone")):
        return "parent_company"
    if any(cue in text for cue in ("合并", "consolidated", "group basis")):
        return "consolidated"
    return default


def _expected_revenue(
    sample_key: str,
    *,
    period: str,
    entity_scope: str,
    truth: dict,
) -> float | None:
    sample = truth["samples"].get(sample_key) or {}
    rev = (sample.get("revenue") or {}).get(entity_scope) or {}
    return rev.get(str(period))


def _patch_case(case: dict, *, sample_key: str, truth: dict, default_scope: str) -> bool:
    changed = False
    scope = _scope_for_question(str(case.get("question") or ""), default_scope)
    if case.get("expect_entity_scope") != scope:
        case["expect_entity_scope"] = scope
        changed = True
    metric_key = case.get("expect_metric_key")
    period = case.get("expect_period")
    if metric_key == "revenue" and period and case.get("expect_value") is not None:
        expected = _expected_revenue(sample_key, period=str(period), entity_scope=scope, truth=truth)
        if expected is not None and float(case["expect_value"]) != float(expected):
            case["expect_value"] = expected
            changed = True
    if scope == "parent_company" and "table_scope" not in (case.get("tags") or []):
        tags = list(case.get("tags") or [])
        tags.append("table_scope")
        case["tags"] = tags
        changed = True
    return changed


def patch_golden_file(path: Path, *, truth: dict, dry_run: bool) -> int:
    sample_key = _infer_sample(path)
    if sample_key is None:
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    default_scope = str(payload.get("default_entity_scope") or truth.get("default_entity_scope") or "consolidated")
    if payload.get("default_entity_scope") != truth.get("default_entity_scope"):
        payload["default_entity_scope"] = truth.get("default_entity_scope", "consolidated")
    changes = 0
    for bucket in ("retrieval_cases", "benchmark_cases", "l4_cases"):
        for case in payload.get(bucket) or []:
            if _patch_case(case, sample_key=sample_key, truth=truth, default_scope=default_scope):
                changes += 1
    if changes and not dry_run:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync golden files with consolidated metric truth")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    truth = _load_truth()
    total = 0
    for filename in SAMPLE_FILES.values():
        path = GOLDEN_DIR / filename
        if not path.exists():
            print(f"skip missing {path}")
            continue
        n = patch_golden_file(path, truth=truth, dry_run=args.dry_run)
        print(f"{'would patch' if args.dry_run else 'patched'} {path.name}: {n} case field(s)")
        total += n
    return 0 if total >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
