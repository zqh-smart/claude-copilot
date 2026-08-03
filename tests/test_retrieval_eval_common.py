from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.retrieval_eval_common import (
    load_retrieval_eval_cases,
    periods_equal,
    resolve_doc_id_from_expectations,
    score_retrieval_case,
    summarize_channel_ablation,
    summarize_retrieval_cases,
    values_equal,
)


def test_values_equal_numeric_tolerance() -> None:
    assert values_equal(931944638, 931944638.0)
    assert values_equal(931944638.5, 931944638)


def test_periods_equal_accepts_fiscal_date_but_rejects_ambiguous_range() -> None:
    assert periods_equal("September 30, 2023", "2023") is True
    assert periods_equal("2023-09-30", 2023) is True
    assert periods_equal("2023/2022", "2023") is False
    assert periods_equal("202021", "2020") is False


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


def test_score_retrieval_case_reports_proxy_ranking_and_failure_category() -> None:
    preview = SimpleNamespace(
        query_analysis=SimpleNamespace(intent="semantic", routes=["vector"]),
        metrics=[],
        hits=[
            SimpleNamespace(
                segment_id="noise",
                content="General company overview",
                metadata={"section_type": "company_overview"},
            ),
            SimpleNamespace(
                segment_id="relevant",
                content="Revenue growth was driven by increased product demand.",
                metadata={"section_type": "management_discussion"},
            ),
        ],
        graph_paths=[],
        warnings=[],
        answer="",
    )
    case = {
        "id": "growth",
        "question": "Why did revenue grow?",
        "expect_route": "semantic",
        "expect_section_types": ["management_discussion"],
        "expect_keywords": ["revenue", "growth"],
    }

    scored = score_retrieval_case(case, preview)

    ranking = scored["ranking"]
    assert ranking["evaluated"] is True
    assert ranking["relevance_source"] == "semantic_proxy"
    assert ranking["relevant_hit_ranks"] == [2]
    assert ranking["hit_rate_at_5"] == 1.0
    assert ranking["reciprocal_rank"] == 0.5
    assert ranking["mrr_at_10"] == 0.5
    assert ranking["ndcg_at_5"] == 0.6309
    assert ranking["ndcg_at_10"] == 0.6309
    assert ranking["recall_at_5"] is None
    assert ranking["hard_negative_rate_at_5"] == 0.0
    assert scored["hit_references"] == [
        {
            "rank": 1,
            "segment_id": "noise",
                "score": None,
                "section_type": "company_overview",
                "segment_fingerprint": None,
                "page_start": None,
            "page_end": None,
            "content_preview": "General company overview",
        },
        {
            "rank": 2,
            "segment_id": "relevant",
                "score": None,
                "section_type": "management_discussion",
                "segment_fingerprint": None,
                "page_start": None,
            "page_end": None,
            "content_preview": "Revenue growth was driven by increased product demand.",
        },
    ]
    assert scored["failure_categories"] == []


def test_score_retrieval_case_uses_explicit_segment_fingerprint() -> None:
    preview = SimpleNamespace(
        query_analysis=SimpleNamespace(intent="semantic", routes=["vector"]),
        metrics=[],
        hits=[
            SimpleNamespace(
                segment_id="new-doc-segment-9",
                score=0.9,
                content="Relevant evidence",
                metadata={"segment_fingerprint": "stable-relevant"},
            )
        ],
        graph_paths=[],
        warnings=[],
        answer="",
    )
    case = {
        "id": "explicit",
        "question": "What happened?",
        "expect_route": "semantic",
        "expect_relevant_segment_fingerprints": ["stable-relevant"],
        "expect_hard_negative_segment_fingerprints": ["stable-negative"],
    }

    scored = score_retrieval_case(case, preview)

    assert scored["ranking"]["relevance_source"] == "explicit_segment_fingerprints"
    assert scored["ranking"]["relevant_hit_ranks"] == [1]
    assert scored["ranking"]["hard_negative_hit_ranks"] == []


def test_retrieval_diagnostics_summarize_routes_ablation_and_failures() -> None:
    cases = [
        {
            "actual_routes": ["vector"],
            "ranking": {
                "evaluated": True,
                "relevance_source": "explicit_segment_ids",
                "hit_rate_at_5": 1.0,
                "reciprocal_rank": 1.0,
                "mrr_at_5": 1.0,
                "mrr_at_10": 1.0,
                "ndcg_at_5": 1.0,
                "ndcg_at_10": 1.0,
                "recall_at_5": 0.5,
                "hard_negative_rate_at_5": 0.0,
                "hard_negative_rate_at_10": 0.0,
            },
            "failure_categories": [],
            "latency_ms": 100,
        },
        {
            "actual_routes": ["vector", "sql"],
            "ranking": {
                "evaluated": True,
                "relevance_source": "semantic_proxy",
                "hit_rate_at_5": 0.0,
                "reciprocal_rank": 0.0,
                "mrr_at_5": 0.0,
                "mrr_at_10": 0.0,
                "ndcg_at_5": 0.0,
                "ndcg_at_10": 0.0,
                "recall_at_5": None,
                "hard_negative_rate_at_5": 1.0,
                "hard_negative_rate_at_10": 1.0,
            },
            "failure_categories": ["semantic_recall"],
            "latency_ms": 200,
        },
        {
            "actual_routes": ["graph"],
            "ranking": {
                "evaluated": False,
                "relevance_source": None,
            },
            "failure_categories": ["graph_path"],
            "expect_abstain": True,
            "abstain_ok": True,
            "latency_ms": 50,
        },
    ]

    diagnostics = summarize_retrieval_cases(cases)

    assert diagnostics["ranking"]["evaluated_cases"] == 2
    assert diagnostics["ranking"]["mrr_at_5"] == 0.5
    assert diagnostics["ranking"]["mrr_at_10"] == 0.5
    assert diagnostics["ranking"]["recall_at_5"] == 0.5
    assert diagnostics["abstention"]["accuracy"] == 1.0
    assert diagnostics["latency_ms"]["p95"] == 200
    assert diagnostics["route_combinations"] == {
        "graph": 1,
        "vector": 1,
        "vector+sql": 1,
    }
    assert diagnostics["route_coverage_ablation"]["vector_only"]["covered"] == 1
    assert diagnostics["route_coverage_ablation"]["all_channels"]["covered"] == 3
    assert diagnostics["failure_categories"] == {
        "graph_path": 1,
        "semantic_recall": 1,
    }


def test_score_retrieval_case_explicit_recall_and_mrr_at_10() -> None:
    hits = [
        SimpleNamespace(
            segment_id=f"s{i}",
            content=f"hit {i}",
            metadata={"segment_fingerprint": fp},
        )
        for i, fp in enumerate(
            ["neg", "rel-a", "other", "rel-b", "x", "y", "z", "w", "v", "u"],
            start=1,
        )
    ]
    preview = SimpleNamespace(
        query_analysis=SimpleNamespace(intent="semantic", routes=["vector"]),
        metrics=[],
        hits=hits,
        graph_paths=[],
        warnings=[],
        answer="",
    )
    case = {
        "id": "ranked",
        "question": "Why?",
        "expect_route": "semantic",
        "expect_relevant_segment_fingerprints": ["rel-a", "rel-b", "rel-c"],
        "expect_hard_negative_segment_fingerprints": ["neg"],
    }
    scored = score_retrieval_case(case, preview)
    assert scored["ranking"]["recall_at_5"] == round(2 / 3, 4)
    assert scored["ranking"]["mrr_at_10"] == 0.5
    assert scored["ranking"]["hard_negative_rate_at_5"] == 1.0
    assert len(scored["hit_references"]) == 10


def test_score_retrieval_case_abstain() -> None:
    preview = SimpleNamespace(
        query_analysis=SimpleNamespace(intent="structured", routes=["sql"]),
        metrics=[SimpleNamespace(metric_key="revenue", period="2021", value=1)],
        hits=[],
        graph_paths=[],
        warnings=[],
        answer="should not answer",
    )
    case = {
        "id": "abstain",
        "question": "2025年营业收入是多少？",
        "expect_route": "structured",
        "expect_abstain": True,
    }
    scored = score_retrieval_case(case, preview)
    assert scored["abstain_ok"] is False
    assert scored["passed"] is False
    assert "abstention" in scored["failure_categories"]

    empty = SimpleNamespace(
        query_analysis=SimpleNamespace(intent="structured", routes=["sql"]),
        metrics=[],
        hits=[],
        graph_paths=[],
        warnings=["SQL route returned no matching financial metrics"],
        answer="",
    )
    assert score_retrieval_case(case, empty)["passed"] is True


def test_load_retrieval_eval_cases_includes_benchmark() -> None:
    expectations = {
        "retrieval_cases": [{"id": "gate"}],
        "benchmark_cases": [{"id": "bench"}],
    }
    assert [c["id"] for c in load_retrieval_eval_cases(expectations)] == ["gate"]
    assert [
        c["id"]
        for c in load_retrieval_eval_cases(expectations, include_benchmark=True)
    ] == ["gate", "bench"]


def test_summarize_channel_ablation() -> None:
    rows = [
        {"channel": "sql_only", "passed": True},
        {"channel": "sql_only", "passed": False},
        {"channel": "vector_only", "passed": True},
    ]
    summary = summarize_channel_ablation(rows)
    assert summary["sql_only"]["pass_rate"] == 0.5
    assert summary["vector_only"]["passed"] == 1
