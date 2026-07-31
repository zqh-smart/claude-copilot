"""LangGraph Reporting lite — single-document outline report (no LLM, no export UI)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, TypedDict

from app.workflows.quant.graph import calculate_from_metrics

_CORE_METRIC_ORDER = (
    "revenue",
    "net_income",
    "net_cash_from_operating_activities",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "gross_profit",
    "operating_income",
    "eps",
    "roe",
)

_MVP_DISCLAIMER = "本报告为提纲 MVP，非正式投研报告。"


class ReportingState(TypedDict, total=False):
    doc_id: str
    company_id: str | None
    company_name: str | None
    question: str | None
    top_k: int
    metrics: list[dict]
    calculations: list[dict]
    risk_findings: list[dict]
    sections: list[dict]
    warnings: list[str]
    answer: str


class _FallbackReportingGraph:
    def __init__(
        self,
        gather_fn: Callable[[dict], dict],
        outline_fn: Callable[[dict], dict],
        format_fn: Callable[[dict], dict],
    ) -> None:
        self._gather_fn = gather_fn
        self._outline_fn = outline_fn
        self._format_fn = format_fn

    def invoke(self, state: dict) -> dict:
        updated = {**state, **self._gather_fn(state)}
        updated = {**updated, **self._outline_fn(updated)}
        return {**updated, **self._format_fn(updated)}


def _format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _metric_sort_key(metric_key: str) -> tuple[int, str]:
    try:
        return (_CORE_METRIC_ORDER.index(metric_key), metric_key)
    except ValueError:
        return (len(_CORE_METRIC_ORDER), metric_key)


def _format_metric_bullet(item: dict) -> str:
    metric_key = str(item.get("metric_key") or "unknown")
    period = item.get("period") or item.get("period_year") or "—"
    value = item.get("value")
    unit = item.get("unit") or ""
    currency = item.get("currency") or ""
    suffix = " ".join(part for part in (unit, currency) if part).strip()
    value_text = f"{value}{f' {suffix}' if suffix else ''}"
    return f"{metric_key}（{period}）：{value_text}"


def select_core_metrics(metrics: list[dict], limit: int = 8) -> list[dict]:
    """Pick representative core metrics ordered by financial importance."""
    if not metrics:
        return []

    by_key: dict[str, list[dict]] = defaultdict(list)
    for item in metrics:
        by_key[str(item.get("metric_key") or "unknown")].append(item)

    selected: list[dict] = []
    for metric_key in sorted(by_key, key=_metric_sort_key):
        candidates = by_key[metric_key]
        best = max(
            candidates,
            key=lambda item: (
                item.get("period_year")
                if item.get("period_year") is not None
                else -1,
                str(item.get("period") or ""),
            ),
        )
        selected.append(best)
        if len(selected) >= limit:
            break
    return selected


def build_report_sections(state: dict) -> list[dict]:
    """Build rule-based outline sections for a single-document report."""
    doc_id = state.get("doc_id") or "—"
    company_name = state.get("company_name") or "未知公司"
    company_id = state.get("company_id")
    question = (state.get("question") or "").strip()
    metrics = list(state.get("metrics") or [])
    calculations = list(state.get("calculations") or [])
    risk_findings = list(state.get("risk_findings") or [])
    warnings = list(state.get("warnings") or [])

    company_bullets = [
        f"文档 ID：{doc_id}",
        f"公司：{company_name}",
    ]
    if company_id:
        company_bullets.append(f"公司 ID：{company_id}")
    if question:
        company_bullets.append(f"报告主题提示：{question}")

    core_metrics = select_core_metrics(metrics)
    if core_metrics:
        metric_bullets = [_format_metric_bullet(item) for item in core_metrics]
    else:
        metric_bullets = ["未检索到结构化财务指标。"]

    growth_bullets: list[str] = []
    trend_calculations = [
        calc
        for calc in calculations
        if (calc.get("yoy_growth") or {}) or calc.get("cagr") is not None
    ]
    if trend_calculations:
        for calc in trend_calculations[:6]:
            metric_key = str(calc.get("metric_key") or "unknown")
            yearly = calc.get("yearly_values") or {}
            yoy = calc.get("yoy_growth") or {}
            cagr = calc.get("cagr")

            if yearly:
                yearly_str = ", ".join(
                    f"{year}: {value:,.4g}" for year, value in sorted(yearly.items())
                )
                growth_bullets.append(f"{metric_key} 年度数值：{yearly_str}")
            if yoy:
                yoy_str = ", ".join(
                    f"{year}: {_format_pct(value)}" for year, value in sorted(yoy.items())
                )
                growth_bullets.append(f"{metric_key} YoY 同比增长：{yoy_str}")
            if cagr is not None:
                growth_bullets.append(f"{metric_key} CAGR：{_format_pct(cagr)}")

    risk_bullets: list[str]
    if risk_findings:
        risk_bullets = []
        for index, finding in enumerate(risk_findings[:8], start=1):
            risk_type = finding.get("risk_type") or "unknown_risk"
            summary = finding.get("summary") or risk_type
            severity = finding.get("severity")
            severity_text = f"（严重度：{severity}）" if severity else ""
            risk_bullets.append(f"{index}. [{risk_type}]{severity_text} {summary}")
    else:
        risk_bullets = ["未检索到风险边（HAS_RISK）。"]

    limitation_bullets = list(warnings[:8])
    limitation_bullets.append(_MVP_DISCLAIMER)

    sections: list[dict] = [
        {"title": "公司与文档", "bullets": company_bullets},
        {"title": "核心财务指标", "bullets": metric_bullets},
    ]
    if growth_bullets:
        sections.append({"title": "增长与趋势", "bullets": growth_bullets})
    sections.extend(
        [
            {"title": "风险提示", "bullets": risk_bullets},
            {"title": "局限与说明", "bullets": limitation_bullets},
        ]
    )
    return sections


def format_report_answer(sections: list[dict], warnings: list[str] | None = None) -> str:
    """Join outline sections into a markdown-like Chinese report."""
    parts: list[str] = ["# 单文档财务提纲报告", ""]
    for index, section in enumerate(sections, start=1):
        title = str(section.get("title") or f"章节{index}")
        parts.append(f"## {index}. {title}")
        for bullet in section.get("bullets") or []:
            parts.append(f"- {bullet}")
        parts.append("")

    extra_warnings = list(warnings or [])
    if extra_warnings and not any(
        section.get("title") == "局限与说明" for section in sections
    ):
        parts.append("## 说明")
        for warning in extra_warnings[:6]:
            parts.append(f"- {warning}")

    return "\n".join(parts).strip()


def _metric_fact_to_dict(fact: Any) -> dict:
    from app.core.db.financial_data_repository import extract_period_year

    payload = fact.model_dump(mode="json")
    payload["period_year"] = extract_period_year(fact.period)
    return payload


def _default_gather_context(state: dict) -> dict:
    from app.api.dependencies import get_document_pipeline_service, get_research_service
    from app.core.db import build_company_id, select_serving_metric_facts_from_document
    from app.workflows.risk.graph import (
        _extract_has_risk_findings,
        _graph_path_to_dict,
        graph as risk_graph,
    )

    doc_id = state["doc_id"]
    question = (state.get("question") or "公司面临哪些风险？").strip()
    top_k = state.get("top_k") or 5
    record = get_document_pipeline_service().get_document(doc_id)
    company_name = state.get("company_name") or record.metadata.company
    company_id = state.get("company_id") or (
        build_company_id(company_name) if company_name else None
    )

    warnings = list(state.get("warnings") or [])
    metrics = list(state.get("metrics") or [])
    calculations = list(state.get("calculations") or [])
    risk_findings = list(state.get("risk_findings") or [])

    if not metrics:
        facts = select_serving_metric_facts_from_document(record)
        metrics = [_metric_fact_to_dict(fact) for fact in facts]
        if not metrics:
            warnings.append("未从文档 financial_schema 加载到 metric_facts。")

    if not calculations and metrics:
        computed, calc_warnings = calculate_from_metrics(metrics)
        calculations = computed
        warnings.extend(calc_warnings)

    if not risk_findings:
        risk_state = {
            "doc_id": doc_id,
            "company_id": company_id,
            "question": question,
            "top_k": top_k,
        }
        try:
            risk_result = risk_graph.invoke(risk_state)
            risk_findings = list(risk_result.get("risk_findings") or [])
            warnings.extend(list(risk_result.get("warnings") or []))
        except Exception as exc:
            warnings.append(f"风险图谱检索失败: {type(exc).__name__}")
            try:
                preview = get_research_service().preview(
                    doc_id=doc_id,
                    question=question,
                    top_k=top_k,
                )
                graph_paths = [
                    _graph_path_to_dict(item) for item in (preview.graph_paths or [])
                ]
                risk_findings = _extract_has_risk_findings(graph_paths)
                warnings.extend(list(preview.warnings or []))
            except Exception as preview_exc:
                warnings.append(f"研究预览风险检索失败: {type(preview_exc).__name__}")

    return {
        "company_id": company_id,
        "company_name": company_name,
        "metrics": metrics,
        "calculations": calculations,
        "risk_findings": risk_findings,
        "warnings": warnings,
    }


def _default_build_outline(state: dict) -> dict:
    return {"sections": build_report_sections(state)}


def _default_format_report(state: dict) -> dict:
    sections = list(state.get("sections") or [])
    warnings = list(state.get("warnings") or [])
    return {"answer": format_report_answer(sections, warnings)}


def build_reporting_graph(
    gather_fn: Callable[[dict], dict] | None = None,
    outline_fn: Callable[[dict], dict] | None = None,
    format_fn: Callable[[dict], dict] | None = None,
):
    gather = gather_fn or _default_gather_context
    outline = outline_fn or _default_build_outline
    format_report = format_fn or _default_format_report
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return _FallbackReportingGraph(gather, outline, format_report)

    builder = StateGraph(ReportingState)
    builder.add_node("gather_context", gather)
    builder.add_node("build_outline", outline)
    builder.add_node("format_report", format_report)
    builder.add_edge(START, "gather_context")
    builder.add_edge("gather_context", "build_outline")
    builder.add_edge("build_outline", "format_report")
    builder.add_edge("format_report", END)
    return builder.compile()


graph = build_reporting_graph()
