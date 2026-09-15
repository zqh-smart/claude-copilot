from app.workflows.quant.graph import (
    build_quant_graph,
    calculate_from_metrics,
)


def test_calculate_from_metrics_yoy_and_cagr() -> None:
    metrics = [
        {
            "metric_key": "revenue",
            "period_year": 2020,
            "value": 100.0,
        },
        {
            "metric_key": "revenue",
            "period_year": 2021,
            "value": 121.0,
        },
        {
            "metric_key": "revenue",
            "period_year": 2022,
            "value": 146.41,
        },
    ]

    calculations, warnings = calculate_from_metrics(metrics)

    assert not warnings
    assert len(calculations) == 1
    calc = calculations[0]
    assert calc["metric_key"] == "revenue"
    assert calc["yearly_values"] == {2020: 100.0, 2021: 121.0, 2022: 146.41}
    assert calc["yoy_growth"][2021] == 0.21
    assert calc["yoy_growth"][2022] == 0.21
    assert calc["cagr"] == 0.21


def test_quant_graph_formats_calculations_without_llm() -> None:
    def retrieve(_state: dict) -> dict:
        return {
            "query_analysis": {
                "intent": "structured",
                "routes": ["sql"],
                "needs_growth": True,
            },
            "metrics": [],
            "calculations": [
                {
                    "metric_key": "revenue",
                    "yearly_values": {2021: 100.0, 2022: 125.0},
                    "yoy_growth": {2022: 0.25},
                    "cagr": 0.25,
                }
            ],
            "warnings": [],
        }

    compiled = build_quant_graph(retrieve_fn=retrieve)
    result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "company_id": "acme",
            "question": "2021-2022 营收同比增长与 CAGR 是多少？",
            "top_k": 5,
        }
    )

    assert result["calculations"][0]["metric_key"] == "revenue"
    assert "revenue" in result["answer"]
    assert "YoY" in result["answer"] or "同比" in result["answer"]
    assert "CAGR" in result["answer"] or "复合" in result["answer"]
    assert "25.00%" in result["answer"]


def test_quant_graph_compute_from_metrics_when_no_calculations() -> None:
    def retrieve(_state: dict) -> dict:
        return {
            "query_analysis": {"intent": "structured", "routes": ["sql"]},
            "metrics": [
                {"metric_key": "net_income", "period_year": 2022, "value": 50.0},
                {"metric_key": "net_income", "period_year": 2023, "value": 60.0},
            ],
            "calculations": [],
            "warnings": [],
        }

    compiled = build_quant_graph(retrieve_fn=retrieve)
    result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "company_id": "acme",
            "question": "净利润 YoY 增长多少？",
            "top_k": 3,
        }
    )

    assert len(result["calculations"]) == 1
    assert result["calculations"][0]["yoy_growth"][2023] == 0.2
    assert "net_income" in result["answer"]
    assert "20.00%" in result["answer"]


def test_quant_graph_empty_metrics_message() -> None:
    def retrieve(_state: dict) -> dict:
        return {
            "query_analysis": {"intent": "semantic", "routes": ["vector"]},
            "metrics": [],
            "calculations": [],
            "warnings": [],
        }

    compiled = build_quant_graph(retrieve_fn=retrieve)
    result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "question": "公司战略是什么？",
            "top_k": 3,
        }
    )

    assert result["calculations"] == []
    assert "未检索到" in result["answer"]
