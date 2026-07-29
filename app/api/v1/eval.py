"""Read-only eval report APIs for the workspace console."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/eval", tags=["eval"])


def _reports_root() -> Path:
    return Path(get_settings().report_data_path)


def _serving_dir() -> Path:
    return _reports_root() / "serving_eval"


def _eval_dir() -> Path:
    return _reports_root() / "eval"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _serving_summary(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    l3 = payload.get("l3") or {}
    return {
        "doc_id": payload.get("doc_id") or path.stem.replace("_serving_eval", ""),
        "path": str(path.as_posix()),
        "ingest_seconds": payload.get("ingest_seconds"),
        "segment_count": payload.get("segment_count"),
        "company_id": payload.get("company_id"),
        "backends": payload.get("backends") or {},
        "embedding_info": payload.get("embedding_info") or {},
        "serving_gate": payload.get("serving_gate") or {},
        "l3": {
            "total": l3.get("total"),
            "passed": l3.get("passed"),
            "pass_rate": l3.get("pass_rate"),
        },
        "mtime": path.stat().st_mtime,
    }


@router.get("/serving")
def list_serving_evals() -> list[dict[str, Any]]:
    directory = _serving_dir()
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*_serving_eval.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        items.append(_serving_summary(path, payload))
    return items


@router.get("/serving/{doc_id}")
def get_serving_eval(doc_id: str) -> dict[str, Any]:
    path = _serving_dir() / f"{doc_id}_serving_eval.json"
    if not path.exists():
        # Allow lookup by scanning if filename differs slightly.
        matches = list(_serving_dir().glob(f"{doc_id}*_serving_eval.json")) if _serving_dir().exists() else []
        if not matches:
            raise HTTPException(status_code=404, detail=f"Serving eval not found for doc_id={doc_id}")
        path = matches[0]
    try:
        payload = _load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read report: {exc}") from exc
    summary = _serving_summary(path, payload)
    l3 = payload.get("l3") or {}
    summary["cases"] = l3.get("cases") or []
    summary["serving_metric_fact_count"] = payload.get("serving_metric_fact_count")
    summary["sql_metric_count"] = payload.get("sql_metric_count")
    return summary


@router.get("/scorecards")
def list_scorecards() -> list[dict[str, Any]]:
    directory = _eval_dir()
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*scorecard*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "name": path.name,
                "path": str(path.as_posix()),
                "summary_scores": payload.get("summary_scores") or {},
                "serving_gate": payload.get("serving_gate") or {},
                "retrieval_case_count": len(payload.get("retrieval_cases") or []),
                "mtime": path.stat().st_mtime,
            }
        )
    return items
