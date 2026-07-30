"""LangGraph Quant Agent — structured metrics, YoY/CAGR, rule-based answer (no LLM)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, TypedDict


class QuantState(TypedDict, total=False):
    doc_id: str
    company_id: str | None
    question: str
    top_k: int
    query_analysis: dict
    metrics: list[dict]
    calculations: list[dict]
    warnings: list[str]
    answer: str


class _FallbackQuantGraph:
    def __init__(
        self,
        retrieve_fn: Callable[[dict], dict],
        compute_fn: Callable[[dict], dict],
        format_fn: Callable[[dict], dict],
    ) -> None:
        self._retrieve_fn = retrieve_fn
        self._compute_fn = compute_fn
        self._format_fn = format_fn

    def invoke(self, state: dict) -> dict:
        updated = {**state, **self._retrieve_fn(state)}
        updated = {**updated, **self._compute_fn(updated)}
        return {**updated, **self._format_fn(updated)}


def _format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _metric_numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def calculate_from_metrics(metrics: list[dict]) -> tuple[list[dict], list[str]]:
    """Compute YoY/CAGR from structured metric observations (orchestrator-compatible)."""
    grouped: dict[str, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for item in metrics:
        period_year = item.get("period_year")
        numeric = _metric_numeric_value(item.get("value"))
        if period_year is not None and numeric is not None:
            grouped[str(item.get("metric_key") or "unknown")][int(period_year)].append(item)

    calculations: list[dict] = []
    warnings: list[str] = []
    for metric_key, by_year in grouped.items():
        yearly_values: dict[int, float] = {}
        for year, candidates in sorted(by_year.items()):
            distinct_values = {
                _metric_numeric_value(candidate.get("value"))
                for candidate in candidates
            }
            distinct_values.discard(None)
            if len(distinct_values) > 1:
                warnings.append(
                    f"{metric_key} {year} 存在 {len(distinct_values)} 个冲突数值，取首条。"
                )
            first_value = _metric_numeric_value(candidates[0].get("value"))
            if first_value is not None:
                yearly_values[year] = first_value

        yoy_growth: dict[int, float] = {}
        years = sorted(yearly_values)
        for previous_year, current_year in zip(years, years[1:], strict=False):
            previous = yearly_values[previous_year]
            if previous != 0:
                yoy_growth[current_year] = round(
                    (yearly_values[current_year] - previous) / abs(previous),
                    6,
                )

        cagr: float | None = None
        if len(years) >= 2:
            first_year, last_year = years[0], years[-1]
            first_value, last_value = yearly_values[first_year], yearly_values[last_year]
            if first_value > 0 and last_value > 0 and last_year > first_year:
                cagr = round(
                    (last_value / first_value) ** (1 / (last_year - first_year)) - 1,
                    6,
                )

        calculations.append(
            {
                "metric_key": metric_key,
                "yearly_values": yearly_values,
                "yoy_growth": yoy_growth,
                "cagr": cagr,
            }
        )
    return calculations, warnings


def _default_retrieve_metrics(state: dict) -> dict:
    from app.api.dependencies import get_document_pipeline_service, get_research_service
    from app.core.db import build_company_id

    doc_id = state["doc_id"]
    question = state["question"]
    top_k = state.get("top_k") or 5
    record = get_document_pipeline_service().get_document(doc_id)
    company_id = state.get("company_id") or (
        build_company_id(record.metadata.company) if record.metadata.company else None
    )

    service = get_research_service()
    retrieved = service._run_retrieval(
        {
            "doc_id": doc_id,
            "company_id": company_id,
            "question": question,
            "top_k": top_k,
        }
    )
    return {
        "company_id": company_id,
        "query_analysis": retrieved.get("query_analysis") or {},
        "metrics": list(retrieved.get("metrics") or []),
        "calculations": list(retrieved.get("calculations") or []),
        "warnings": list(retrieved.get("warnings") or []),
    }


def _default_compute_quant(state: dict) -> dict:
    calculations = list(state.get("calculations") or [])
    if calculations:
        return {"calculations": calculations}

    metrics = list(state.get("metrics") or [])
    if not metrics:
        return {
            "calculations": [],
            "warnings": [
                *list(state.get("warnings") or []),
                "未检索到可用于定量分析的结构化指标。",
            ],
        }

    computed, extra_warnings = calculate_from_metrics(metrics)
    return {
        "calculations": computed,
        "warnings": [*list(state.get("warnings") or []), *extra_warnings],
    }


def _default_format_answer(state: dict) -> dict:
    calculations = list(state.get("calculations") or [])
    metrics = list(state.get("metrics") or [])
    warnings = list(state.get("warnings") or [])
    query_analysis = state.get("query_analysis") or {}

    parts: list[str] = []
    intent = query_analysis.get("intent")
    if intent:
        parts.append(f"查询意图：{intent}")

    if calculations:
        parts.append(f"\n定量分析结果（{len(calculations)} 项指标）：")
        for index, calc in enumerate(calculations, start=1):
            metric_key = str(calc.get("metric_key") or "unknown")
            yearly = calc.get("yearly_values") or {}
            yoy = calc.get("yoy_growth") or {}
            cagr = calc.get("cagr")

            parts.append(f"\n{index}. {metric_key}")
            if yearly:
                yearly_str = ", ".join(
                    f"{year}: {value:,.4g}" for year, value in sorted(yearly.items())
                )
                parts.append(f"   年度数值: {yearly_str}")
            if yoy:
                yoy_str = ", ".join(
                    f"{year}: {_format_pct(value)}" for year, value in sorted(yoy.items())
                )
                parts.append(f"   同比增长 (YoY): {yoy_str}")
            if cagr is not None:
                parts.append(f"   复合年均增长 (CAGR): {_format_pct(cagr)}")
    elif metrics:
        parts.append("\n结构化指标（未计算增长率）：")
        for item in metrics[:10]:
            metric_key = item.get("metric_key") or "unknown"
            period = item.get("period") or item.get("period_year") or "—"
            value = item.get("value")
            unit = item.get("unit") or ""
            currency = item.get("currency") or ""
            suffix = " ".join(part for part in (unit, currency) if part).strip()
            parts.append(f"- {metric_key} ({period}): {value}{f' {suffix}' if suffix else ''}")
    else:
        parts.append("\n未检索到可用于定量分析的结构化指标。")

    if warnings:
        parts.append("\n说明：")
        for warning in warnings[:6]:
            parts.append(f"- {warning}")

    return {"answer": "\n".join(parts).strip()}


def build_quant_graph(
    retrieve_fn: Callable[[dict], dict] | None = None,
    compute_fn: Callable[[dict], dict] | None = None,
    format_fn: Callable[[dict], dict] | None = None,
):
    retrieve = retrieve_fn or _default_retrieve_metrics
    compute = compute_fn or _default_compute_quant
    format_answer = format_fn or _default_format_answer
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return _FallbackQuantGraph(retrieve, compute, format_answer)

    builder = StateGraph(QuantState)
    builder.add_node("retrieve_metrics", retrieve)
    builder.add_node("compute_quant", compute)
    builder.add_node("format_answer", format_answer)
    builder.add_edge(START, "retrieve_metrics")
    builder.add_edge("retrieve_metrics", "compute_quant")
    builder.add_edge("compute_quant", "format_answer")
    builder.add_edge("format_answer", END)
    return builder.compile()


graph = build_quant_graph()
