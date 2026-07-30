from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.retrieval_eval_common import (
    resolve_doc_id_from_expectations,
    score_retrieval_case,
    values_equal,
)


def test_values_equal_numeric_tolerance() -> None:
    assert values_equal(931944638, 931944638.0)
    assert values_equal(931944638.5, 931944638)


def test_resolve_doc_id_prefers_company_match(tmp_path) -> None:
    serving_dir = tmp_path / "serving_eval"
    serving_dir.mkdir()
    tianhua = {
        "doc_id": "c97881e5040349a4ac6e19124b3b5f26",
        "serving_gate": {"summary": {"company": "苏州天华新能源科技股份有限公司", "year": 2021}},
    }
    znz = {
        "doc_id": "9e3c98ab748645d8b8db9cd49da870cd",
        "serving_gate": {"summary": {"company": "北京指南针科技发展股份有限公司", "year": 2021}},
    }
    (serving_dir / "c97881e5040349a4ac6e19124b3b5f26_serving_eval.json").write_text(
        json.dumps(tianhua),
        encoding="utf-8",
    )
    (serving_dir / "9e3c98ab748645d8b8db9cd49da870cd_serving_eval.json").write_text(
        json.dumps(znz),
        encoding="utf-8",
    )

    expectations = {
        "document_key": "znz_2021_annual_report",
        "notes": {"company": "北京指南针科技发展股份有限公司", "year": 2021},
    }
    resolved = resolve_doc_id_from_expectations(
        doc_id=None,
        expectations=expectations,
        serving_eval_dir=serving_dir,
    )
    assert resolved == "9e3c98ab748645d8b8db9cd49da870cd"


def test_score_retrieval_case_graph_requires_relation_type() -> None:
    preview = SimpleNamespace(
        query_analysis=SimpleNamespace(intent="relational", routes=["graph"]),
        metrics=[],
        hits=[],
        graph_paths=[
            {
                "relationships": [
                    {"relationship_type": "EVIDENCED_BY"},
                ]
            }
        ],
        warnings=[],
        answer="risk text",
    )
    case = {
        "id": "q_market_risk_graph",
        "question": "公司面临哪些市场风险或风险暴露？",
        "expect_route": "graph",
        "expect_graph_relation_types": ["HAS_RISK"],
    }
    scored = score_retrieval_case(case, preview)
    assert scored["graph_ok"] is False
    assert scored["passed"] is False


def test_score_retrieval_case_structured_metric_match() -> None:
    preview = SimpleNamespace(
        query_analysis=SimpleNamespace(intent="structured", routes=["sql"]),
        metrics=[
            SimpleNamespace(metric_key="revenue", period="2021", value=931944638),
        ],
        hits=[],
        graph_paths=[],
        warnings=[],
        answer="revenue(2021)=931944638",
    )
    case = {
        "id": "q_revenue_2021",
        "question": "2021年营业收入是多少？",
        "expect_route": "structured",
        "expect_metric_key": "revenue",
        "expect_period": "2021",
        "expect_value": 931944638,
    }
    scored = score_retrieval_case(case, preview)
    assert scored["metric_ok"] is True
    assert scored["route_ok"] is True
    assert scored["passed"] is True
