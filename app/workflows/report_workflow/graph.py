"""§5.5 Report Generation Workflow lite (no UI / no file export).

Flow: prepare → build_report → quant_snapshot → compose_answer
"""

from __future__ import annotations

from typing import Callable, TypedDict


class ReportWorkflowState(TypedDict, total=False):
    doc_id: str
    company_id: str | None
    question: str
    top_k: int
    report_answer: str
    report_sections: list[dict]
    calculations: list[dict]
    metrics: list[dict]
    quant_summary: str
    warnings: list[str]
    answer: str


class _FallbackReportWorkflow:
    def __init__(self, steps: list[Callable[[dict], dict]]) -> None:
        self._steps = steps

    def invoke(self, state: dict) -> dict:
        updated = dict(state)
        for step in self._steps:
            updated = {**updated, **step(updated)}
        return updated


def _format_quant_summary(calculations: list[dict]) -> str:
    if not calculations:
        return "无多期增长计算"
    lines: list[str] = []
    for calc in calculations[:4]:
        metric_key = str(calc.get("metric_key") or "unknown")
        yoy = calc.get("yoy_growth") or {}
        cagr = calc.get("cagr")
        bits: list[str] = []
        if yoy:
            year, rate = sorted(yoy.items())[-1]
            bits.append(f"YoY {year}={float(rate) * 100:.2f}%")
        if cagr is not None:
            bits.append(f"CAGR={float(cagr) * 100:.2f}%")
        lines.append(f"- {metric_key}：" + ("；".join(bits) if bits else "仅有单期数据"))
    return "\n".join(lines)


def compose_report_workflow_answer(
    *,
    report_answer: str,
    quant_summary: str,
    warnings: list[str],
) -> str:
    parts = [
        "【§5.5 自动报告工作流 · lite】",
        "",
        "## A. 提纲正文",
        report_answer.strip() or "（无提纲）",
        "",
        "## B. 增长快照（Quant）",
        quant_summary.strip() or "无",
    ]
    if warnings:
        parts.extend(["", "## C. 工作流说明"])
        for warning in warnings[:8]:
            parts.append(f"- {warning}")
    parts.append("")
    parts.append("（工作流 lite：输出 Markdown 提纲，无 PDF/报告中心）")
    return "\n".join(parts).strip()


def _default_prepare(state: dict) -> dict:
    warnings = list(state.get("warnings") or [])
    if not state.get("doc_id"):
        warnings.append("report_workflow 需要 doc_id。")
    return {"warnings": warnings}


def _default_build_report(state: dict) -> dict:
    from app.workflows.reporting.graph import graph as reporting_graph

    warnings = list(state.get("warnings") or [])
    doc_id = state.get("doc_id")
    if not doc_id:
        return {"report_answer": "", "report_sections": [], "warnings": warnings}
    try:
        result = reporting_graph.invoke(
            {
                "doc_id": doc_id,
                "company_id": state.get("company_id"),
                "question": state.get("question") or "",
                "top_k": state.get("top_k") or 5,
            }
        )
        warnings.extend(list(result.get("warnings") or []))
        return {
            "report_answer": str(result.get("answer") or ""),
            "report_sections": list(result.get("sections") or []),
            "calculations": list(result.get("calculations") or []),
            "warnings": warnings,
        }
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"reporting 调用失败: {type(exc).__name__}")
        return {"report_answer": "", "report_sections": [], "warnings": warnings}


def _default_quant_snapshot(state: dict) -> dict:
    from app.workflows.quant.graph import calculate_from_metrics

    warnings = list(state.get("warnings") or [])
    calculations = list(state.get("calculations") or [])
    if calculations:
        return {"quant_summary": _format_quant_summary(calculations), "warnings": warnings}

    # Fallback: compute from reporting metrics if present in sections path — skip DB.
    metrics = list(state.get("metrics") or [])
    if metrics:
        computed, calc_warnings = calculate_from_metrics(metrics)
        warnings.extend(calc_warnings)
        return {"quant_summary": _format_quant_summary(computed), "warnings": warnings}
    return {"quant_summary": "无多期增长计算", "warnings": warnings}


def _default_compose(state: dict) -> dict:
    return {
        "answer": compose_report_workflow_answer(
            report_answer=str(state.get("report_answer") or ""),
            quant_summary=str(state.get("quant_summary") or ""),
            warnings=list(state.get("warnings") or []),
        )
    }


def build_report_workflow_graph(
    *,
    prepare_fn: Callable[[dict], dict] | None = None,
    report_fn: Callable[[dict], dict] | None = None,
    quant_fn: Callable[[dict], dict] | None = None,
    compose_fn: Callable[[dict], dict] | None = None,
):
    prepare = prepare_fn or _default_prepare
    report = report_fn or _default_build_report
    quant = quant_fn or _default_quant_snapshot
    compose = compose_fn or _default_compose
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return _FallbackReportWorkflow([prepare, report, quant, compose])

    builder = StateGraph(ReportWorkflowState)
    builder.add_node("prepare", prepare)
    builder.add_node("build_report", report)
    builder.add_node("quant_snapshot", quant)
    builder.add_node("compose_answer", compose)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "build_report")
    builder.add_edge("build_report", "quant_snapshot")
    builder.add_edge("quant_snapshot", "compose_answer")
    builder.add_edge("compose_answer", END)
    return builder.compile()


graph = build_report_workflow_graph()
