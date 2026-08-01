"""§5.4 Comparison Workflow lite (no UI / no PDF).

Flow: prepare → compare_metrics → risk_snapshots → compose_answer
"""

from __future__ import annotations

from typing import Callable, TypedDict


class ComparisonWorkflowState(TypedDict, total=False):
    doc_id_a: str
    doc_id_b: str
    question: str
    period: str | int
    metric_keys: list[str]
    compare_answer: str
    compare_matrix: list[dict]
    compare_highlights: list[str]
    risk_summary_a: str
    risk_summary_b: str
    warnings: list[str]
    answer: str


class _FallbackComparisonWorkflow:
    def __init__(self, steps: list[Callable[[dict], dict]]) -> None:
        self._steps = steps

    def invoke(self, state: dict) -> dict:
        updated = dict(state)
        for step in self._steps:
            updated = {**updated, **step(updated)}
        return updated


def _count_risk_types(findings: list[dict]) -> str:
    if not findings:
        return "未命中 HAS_RISK"
    types: list[str] = []
    seen: set[str] = set()
    for item in findings:
        risk_type = str(item.get("risk_type") or "unknown")
        if risk_type in seen:
            continue
        seen.add(risk_type)
        types.append(risk_type)
    return f"{len(findings)} 条 · " + "、".join(types[:6])


def compose_comparison_workflow_answer(
    *,
    compare_answer: str,
    risk_summary_a: str,
    risk_summary_b: str,
    warnings: list[str],
) -> str:
    parts = [
        "【§5.4 对比分析工作流 · lite】",
        "",
        "## 1. 财务指标对比",
        compare_answer.strip() or "（无对比结果）",
        "",
        "## 2. 风险对照（图谱 HAS_RISK）",
        f"- 文档 A：{risk_summary_a or '未检索'}",
        f"- 文档 B：{risk_summary_b or '未检索'}",
    ]
    if warnings:
        parts.extend(["", "## 3. 说明"])
        for warning in warnings[:8]:
            parts.append(f"- {warning}")
    parts.append("")
    parts.append("（工作流 lite：无导出、无对比平台 UI）")
    return "\n".join(parts).strip()


def _default_prepare(state: dict) -> dict:
    warnings = list(state.get("warnings") or [])
    if not state.get("doc_id_a") or not state.get("doc_id_b"):
        warnings.append("comparison_workflow 需要 doc_id_a 与 doc_id_b。")
    return {"warnings": warnings}


def _default_compare_metrics(state: dict) -> dict:
    from app.workflows.comparator.graph import graph as comparator_graph

    warnings = list(state.get("warnings") or [])
    doc_id_a = state.get("doc_id_a")
    doc_id_b = state.get("doc_id_b")
    if not doc_id_a or not doc_id_b:
        return {
            "compare_answer": (
                "未配置 doc_id_a/doc_id_b，无法对比；"
                "未生成第二家公司指标或差额。"
            ),
            "compare_matrix": [],
            "compare_highlights": [],
            "warnings": warnings,
        }
    try:
        result = comparator_graph.invoke(
            {
                "doc_id_a": doc_id_a,
                "doc_id_b": doc_id_b,
                "question": state.get("question") or "",
                "period": state.get("period"),
                "metric_keys": state.get("metric_keys"),
            }
        )
        warnings.extend(list(result.get("warnings") or []))
        return {
            "compare_answer": str(result.get("answer") or ""),
            "compare_matrix": list(result.get("matrix") or []),
            "compare_highlights": list(result.get("highlights") or []),
            "warnings": warnings,
        }
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"comparator 调用失败: {type(exc).__name__}")
        return {
            "compare_answer": "",
            "compare_matrix": [],
            "compare_highlights": [],
            "warnings": warnings,
        }


def _default_risk_snapshots(state: dict) -> dict:
    warnings = list(state.get("warnings") or [])
    if not state.get("doc_id_a") or not state.get("doc_id_b"):
        return {
            "risk_summary_a": "未配置文档",
            "risk_summary_b": "未配置文档",
            "warnings": warnings,
        }

    from app.workflows.risk.graph import graph as risk_graph

    question = state.get("question") or "公司面临哪些市场风险或风险暴露？"

    def _snapshot(doc_id: str | None, label: str) -> str:
        if not doc_id:
            return "未配置文档"
        try:
            result = risk_graph.invoke(
                {"doc_id": doc_id, "question": question, "top_k": 5}
            )
            findings = list(result.get("risk_findings") or [])
            warnings.extend(list(result.get("warnings") or []))
            return _count_risk_types(findings)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{label} 风险快照失败: {type(exc).__name__}")
            return "检索失败"

    return {
        "risk_summary_a": _snapshot(state.get("doc_id_a"), "文档A"),
        "risk_summary_b": _snapshot(state.get("doc_id_b"), "文档B"),
        "warnings": warnings,
    }


def _default_compose(state: dict) -> dict:
    warnings = list(state.get("warnings") or [])
    if not state.get("doc_id_a") or not state.get("doc_id_b"):
        parts = [
            "【§5.4 对比分析工作流 · lite】",
            "未配置文档：对比需要 doc_id_a 与 doc_id_b。",
            "未生成第二家公司指标；不会臆造对比结果，请补齐后重试。",
        ]
        if warnings:
            parts.append("说明：")
            parts.extend(f"- {w}" for w in warnings[:8])
        return {"answer": "\n".join(parts).strip()}
    return {
        "answer": compose_comparison_workflow_answer(
            compare_answer=str(state.get("compare_answer") or ""),
            risk_summary_a=str(state.get("risk_summary_a") or ""),
            risk_summary_b=str(state.get("risk_summary_b") or ""),
            warnings=warnings,
        )
    }


def build_comparison_workflow_graph(
    *,
    prepare_fn: Callable[[dict], dict] | None = None,
    compare_fn: Callable[[dict], dict] | None = None,
    risk_fn: Callable[[dict], dict] | None = None,
    compose_fn: Callable[[dict], dict] | None = None,
):
    prepare = prepare_fn or _default_prepare
    compare = compare_fn or _default_compare_metrics
    risk = risk_fn or _default_risk_snapshots
    compose = compose_fn or _default_compose
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return _FallbackComparisonWorkflow([prepare, compare, risk, compose])

    builder = StateGraph(ComparisonWorkflowState)
    builder.add_node("prepare", prepare)
    builder.add_node("compare_metrics", compare)
    builder.add_node("risk_snapshots", risk)
    builder.add_node("compose_answer", compose)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "compare_metrics")
    builder.add_edge("compare_metrics", "risk_snapshots")
    builder.add_edge("risk_snapshots", "compose_answer")
    builder.add_edge("compose_answer", END)
    return builder.compile()


graph = build_comparison_workflow_graph()
