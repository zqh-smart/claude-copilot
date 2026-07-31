from app.workflows.reporting.graph import (
    build_report_sections,
    build_reporting_graph,
    format_report_answer,
    select_core_metrics,
)


def test_select_core_metrics_prefers_key_order() -> None:
    metrics = [
        {"metric_key": "total_assets", "period_year": 2023, "value": 500.0},
        {"metric_key": "revenue", "period_year": 2023, "value": 100.0},
        {"metric_key": "net_income", "period_year": 2022, "value": 10.0},
        {"metric_key": "net_income", "period_year": 2023, "value": 12.0},
    ]

    selected = select_core_metrics(metrics, limit=3)

    assert [item["metric_key"] for item in selected] == [
        "revenue",
        "net_income",
        "total_assets",
    ]
    assert selected[1]["period_year"] == 2023


def test_reporting_graph_outline_contains_core_sections() -> None:
    def gather(_state: dict) -> dict:
        return {
            "company_name": "ACME",
            "company_id": "acme",
            "metrics": [
                {
                    "metric_key": "revenue",
                    "period": "2023",
                    "period_year": 2023,
                    "value": 100.0,
                    "currency": "CNY",
                }
            ],
            "calculations": [],
            "risk_findings": [],
            "warnings": [],
        }

    compiled = build_reporting_graph(gather_fn=gather)
    result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "question": "营收概况",
            "top_k": 5,
        }
    )

    section_titles = [section["title"] for section in result["sections"]]
    assert "核心财务指标" in section_titles
    assert "局限与说明" in section_titles
    assert "核心财务指标" in result["answer"]
    assert "局限" in result["answer"] or "说明" in result["answer"]
    assert "本报告为提纲 MVP" in result["answer"]


def test_reporting_graph_includes_trends_and_risks() -> None:
    def gather(_state: dict) -> dict:
        return {
            "company_name": "ACME",
            "metrics": [
                {"metric_key": "revenue", "period_year": 2022, "value": 100.0},
                {"metric_key": "revenue", "period_year": 2023, "value": 125.0},
            ],
            "calculations": [
                {
                    "metric_key": "revenue",
                    "yearly_values": {2022: 100.0, 2023: 125.0},
                    "yoy_growth": {2023: 0.25},
                    "cagr": 0.25,
                }
            ],
            "risk_findings": [
                {
                    "risk_type": "liquidity_risk",
                    "severity": "medium",
                    "summary": "流动性压力上升",
                    "evidence": "短期借款增加",
                    "relation": "HAS_RISK",
                }
            ],
            "warnings": [],
        }

    compiled = build_reporting_graph(gather_fn=gather)
    result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "question": "增长与风险",
            "top_k": 5,
        }
    )

    section_titles = [section["title"] for section in result["sections"]]
    assert "增长与趋势" in section_titles
    assert "风险提示" in section_titles

    trend_section = next(
        section for section in result["sections"] if section["title"] == "增长与趋势"
    )
    risk_section = next(
        section for section in result["sections"] if section["title"] == "风险提示"
    )
    trend_text = " ".join(trend_section["bullets"])
    risk_text = " ".join(risk_section["bullets"])

    assert "YoY" in trend_text or "同比" in trend_text
    assert "CAGR" in trend_text or "复合" in trend_text
    assert "liquidity_risk" in risk_text
    assert "YoY" in result["answer"] or "同比" in result["answer"]
    assert "liquidity_risk" in result["answer"]


def test_reporting_graph_empty_metrics_still_produces_skeleton() -> None:
    def gather(_state: dict) -> dict:
        return {
            "company_name": "ACME",
            "metrics": [],
            "calculations": [],
            "risk_findings": [],
            "warnings": ["未加载到指标。"],
        }

    compiled = build_reporting_graph(gather_fn=gather)
    result = compiled.invoke(
        {
            "doc_id": "doc-empty",
            "question": "概览",
            "top_k": 3,
        }
    )

    assert result["sections"]
    assert result["answer"].strip()
    assert "核心财务指标" in result["answer"]
    assert "未检索到" in result["answer"] or "未加载" in result["answer"]
    assert "本报告为提纲 MVP" in result["answer"]


def test_build_report_sections_and_format_helpers() -> None:
    sections = build_report_sections(
        {
            "doc_id": "doc-1",
            "company_name": "ACME",
            "metrics": [],
            "calculations": [],
            "risk_findings": [],
            "warnings": ["测试警告"],
        }
    )
    answer = format_report_answer(sections, ["额外说明"])

    assert sections[-1]["title"] == "局限与说明"
    assert any("测试警告" in bullet for bullet in sections[-1]["bullets"])
    assert answer.startswith("# 单文档财务提纲报告")
