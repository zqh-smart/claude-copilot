"""Expand GraphRAG gold query fixtures into a large eval set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURE = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "graph_rag_gold_queries.json"


def load_graph_rag_gold_fixture(path: Path | None = None) -> dict[str, Any]:
    target = path or _FIXTURE
    return json.loads(target.read_text(encoding="utf-8"))


def expand_graph_rag_cases(fixture: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Cartesian product of doc slots and question templates (100+ cases)."""
    data = fixture or load_graph_rag_gold_fixture()
    slots = list(data.get("doc_slots") or [])
    templates = list(data.get("templates") or [])
    static_cases = list(data.get("cases") or [])

    expanded: list[dict[str, Any]] = []
    for slot in slots:
        company = str(slot.get("company_label") or slot.get("slot") or "公司")
        document_key = slot.get("document_key")
        for template in templates:
            prefix = str(template.get("id_prefix") or "graph")
            slot_id = str(slot.get("slot") or "doc")
            case_id = f"{prefix}_{slot_id}"
            question_tpl = str(template.get("question") or "")
            question = question_tpl.format(company=company)
            case: dict[str, Any] = {
                "id": case_id,
                "document_key": document_key,
                "question": question,
                "expect_routes": list(template.get("expect_routes") or []),
                "tags": list(template.get("tags") or []) + [slot_id],
            }
            if template.get("expect_graph_relation_types"):
                case["expect_graph_relation_types"] = list(
                    template["expect_graph_relation_types"]
                )
            if template.get("expect_path_types"):
                case["expect_path_types"] = list(template["expect_path_types"])
            expanded.append(case)

    seen_ids = {case["id"] for case in expanded}
    for case in static_cases:
        if case.get("id") in seen_ids:
            continue
        expanded.append(dict(case))
    return expanded
