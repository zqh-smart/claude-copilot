"""Messages-compatible LangGraph agent for Agent Chat UI.

Exposes graph id ``agent`` via ``langgraph.json`` / ``langgraph dev`` (port 2024).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.config import get_settings


class AgentChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    doc_id: str | None
    doc_id_b: str | None


def _latest_human_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict) and item.get("type") == "text":
                        parts.append(str(item.get("text") or ""))
                return "\n".join(part for part in parts if part).strip()
    return ""


def _resolve_doc_id(state: AgentChatState, config: RunnableConfig | None) -> str | None:
    if state.get("doc_id"):
        return str(state["doc_id"])
    configurable = (config or {}).get("configurable") or {}
    if configurable.get("doc_id"):
        return str(configurable["doc_id"])
    settings = get_settings()
    if settings.agent_chat_doc_id:
        return settings.agent_chat_doc_id.strip() or None
    return _latest_serving_doc_id()


def _resolve_doc_id_b(state: AgentChatState, config: RunnableConfig | None) -> str | None:
    if state.get("doc_id_b"):
        return str(state["doc_id_b"])
    configurable = (config or {}).get("configurable") or {}
    if configurable.get("doc_id_b"):
        return str(configurable["doc_id_b"])
    settings = get_settings()
    if settings.agent_chat_doc_id_b:
        return settings.agent_chat_doc_id_b.strip() or None
    return None


def _latest_serving_doc_id() -> str | None:
    settings = get_settings()
    directory = Path(settings.report_data_path) / "serving_eval"
    if not directory.exists():
        return None
    paths = sorted(directory.glob("*_serving_eval.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        doc_id = payload.get("doc_id")
        if doc_id:
            return str(doc_id)
    return None


def _metric_rows(metrics: list[Any]) -> list[tuple[str, str, Any]]:
    rows: list[tuple[str, str, Any]] = []
    for item in metrics:
        if isinstance(item, dict):
            key = str(item.get("metric_key") or "")
            period = str(item.get("period") or "")
            value = item.get("value")
        else:
            key = str(getattr(item, "metric_key", None) or "")
            period = str(getattr(item, "period", None) or "")
            value = getattr(item, "value", None)
        if key:
            rows.append((key, period, value))
    return rows


def _prefer_primary_metrics(rows: list[tuple[str, str, Any]]) -> list[tuple[str, str, Any]]:
    """Keep one value per (metric_key, period); prefer larger absolute numerics.

    Avoids noisy companions like revenue=4.35 when revenue=469378042.95 exists.
    """
    best: dict[tuple[str, str], tuple[str, str, Any]] = {}
    for key, period, value in rows:
        slot = (key, period)
        prev = best.get(slot)
        if prev is None:
            best[slot] = (key, period, value)
            continue
        prev_num = prev[2] if isinstance(prev[2], (int, float)) and not isinstance(prev[2], bool) else None
        cur_num = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        if cur_num is not None and (prev_num is None or abs(cur_num) > abs(prev_num)):
            best[slot] = (key, period, value)
    return list(best.values())


def _humanize_warning(warning: str) -> str:
    lower = warning.lower()
    if "502" in warning or "bad gateway" in lower:
        return "本地 LLM 暂时不可用（chat 502）。已保留结构化检索结果，可稍后重试合成。"
    if "timed out" in lower or "timeout" in lower:
        return "本地 LLM 超时。已保留结构化检索结果，可稍后重试合成。"
    if "conflicting revenue" in lower or "conflicting" in lower:
        return "同指标存在多条候选；已优先保留金额更大的主值。"
    if "company scope" in lower or "resolved from company scope" in lower:
        return "结构化指标来自公司范围回退（当前文档未命中时可查同公司其它年报）。"
    return warning


def _format_risk_answer(result: dict[str, Any]) -> str:
    answer = str(result.get("answer") or "").strip()
    findings = list(result.get("risk_findings") or [])
    parts = ["【风险分析 · Risk Agent】"]
    if answer:
        parts.append(answer)
    elif findings:
        parts.append(f"识别到 {len(findings)} 条 HAS_RISK 关联。")
    else:
        parts.append("未检索到图谱风险边；请确认文档已 Serving 入库且含风险披露。")
    warnings = [str(item) for item in (result.get("warnings") or []) if item]
    if warnings:
        parts.append("\n说明：")
        seen: set[str] = set()
        for warning in warnings[:4]:
            text = _humanize_warning(warning)
            if text in seen:
                continue
            seen.add(text)
            parts.append(f"- {text}")
    return "\n".join(parts).strip()


def _invoke_chat_specialist(
    *,
    agent_used: str,
    question: str,
    doc_id: str,
    doc_id_b: str | None,
    company_id: str | None,
) -> str:
    """Run one specialist for agent chat; shared by primary and secondary intents."""
    from app.api.dependencies import get_research_service

    if agent_used == "risk":
        from app.workflows.risk.graph import graph as risk_graph

        return _format_risk_answer(
            risk_graph.invoke(
                {
                    "doc_id": doc_id,
                    "company_id": company_id,
                    "question": question,
                    "top_k": 5,
                }
            )
        )
    if agent_used == "compare":
        from app.workflows.comparison_workflow.graph import graph as comparison_workflow

        if not doc_id_b:
            return (
                "【对比 · Comparator】未配置第二份文档。"
                "请设置环境变量 AGENT_CHAT_DOC_ID_B，"
                "或在 LangGraph configurable 中传入 doc_id_b。"
            )
        result = comparison_workflow.invoke(
            {
                "doc_id_a": doc_id,
                "doc_id_b": doc_id_b,
                "question": question,
            }
        )
        return str(result.get("answer") or "").strip() or "【对比】未生成对比结果。"
    if agent_used == "quant":
        from app.workflows.quant.graph import graph as quant_graph

        quant_result = quant_graph.invoke(
            {
                "doc_id": doc_id,
                "company_id": company_id,
                "question": question,
                "top_k": 5,
            }
        )
        answer = str(quant_result.get("answer") or "").strip()
        content = f"【量化 · Quant Agent】\n{answer}" if answer else "【量化 · Quant Agent】未生成计算结果。"
        warnings = quant_result.get("warnings") or []
        if warnings:
            content += "\n说明：\n" + "\n".join(
                f"- {_humanize_warning(str(w))}" for w in warnings[:4]
            )
        return content
    if agent_used == "report":
        from app.workflows.report_workflow.graph import graph as report_workflow

        report_result = report_workflow.invoke(
            {
                "doc_id": doc_id,
                "company_id": company_id,
                "question": question,
                "top_k": 5,
            }
        )
        return str(report_result.get("answer") or "").strip() or "【报告提纲】未生成提纲。"

    preview = get_research_service().preview(doc_id=doc_id, question=question, top_k=5)
    content = _format_answer(preview)
    if agent_used == "structured":
        content = f"【结构化 · Structured Agent】\n{content}"
    return content


_ROUTE_LABELS = {"vector": "语义", "sql": "结构化", "graph": "图谱"}
_INTENT_LABELS = {
    "semantic": "语义检索",
    "structured": "结构化查询",
    "relational": "关系查询",
    "hybrid": "混合检索",
}


def _fusion_field(fusion: Any, name: str) -> Any:
    value = getattr(fusion, name, None)
    if value is not None:
        return value
    if isinstance(fusion, dict):
        return fusion.get(name)
    return None


def _append_fusion_summary(parts: list[str], preview: Any) -> None:
    fusion = getattr(preview, "fusion_summary", None)
    if fusion is None:
        return
    summary = str(_fusion_field(fusion, "summary") or "").strip()
    highlights = list(_fusion_field(fusion, "highlights") or [])
    intent = str(_fusion_field(fusion, "query_intent") or "")
    routes = list(_fusion_field(fusion, "routes") or [])
    if not summary and not highlights:
        return
    parts.append("\n混合检索摘要：")
    if intent or routes:
        labeled_routes = [_ROUTE_LABELS.get(route, route) for route in routes]
        intent_text = _INTENT_LABELS.get(intent, intent)
        if labeled_routes:
            parts.append(f"- 通道：{intent_text}（{' · '.join(labeled_routes)}）")
        elif intent_text:
            parts.append(f"- 通道：{intent_text}")
    if summary:
        parts.append(f"- {summary}")
    for item in highlights[:4]:
        parts.append(f"- {item}")


def _format_answer(preview: Any) -> str:
    synthesis = getattr(preview, "synthesis", None)
    synthesis_answer = ""
    if synthesis is not None and getattr(synthesis, "answer", None):
        synthesis_answer = str(synthesis.answer).strip()
    raw_answer = (getattr(preview, "answer", None) or "").strip()
    metrics = getattr(preview, "metrics", None) or []
    warnings = [str(item) for item in (getattr(preview, "warnings", None) or [])]
    llm_failed = any(
        ("502" in item) or ("timed out" in item.lower()) or ("timeout" in item.lower()) or ("grounded synthesis failed" in item.lower())
        for item in warnings
    )
    primary = _prefer_primary_metrics(_metric_rows(list(metrics)))

    if synthesis_answer and not llm_failed:
        lead = synthesis_answer
    elif primary:
        key, period, value = primary[0]
        lead = f"{period}年{key}为 {value}。" if period.isdigit() else f"{key}（{period}）为 {value}。"
        if llm_failed:
            lead += "（文本合成暂不可用，以下为检索到的主指标）"
    else:
        lead = raw_answer or "（未生成文本答案；见下方证据摘要）"

    parts = [lead]
    if primary:
        parts.append("\n结构化指标：")
        for key, period, value in primary[:8]:
            parts.append(f"- {key} · {period} = {value}")
    if warnings:
        parts.append("\n说明：")
        seen: set[str] = set()
        for warning in warnings[:8]:
            text = _humanize_warning(warning)
            if text in seen:
                continue
            seen.add(text)
            parts.append(f"- {text}")
            if len(seen) >= 4:
                break
    _append_fusion_summary(parts, preview)
    analysis = getattr(preview, "query_analysis", None)
    if analysis is not None and getattr(preview, "fusion_summary", None) is None:
        intent = getattr(analysis, "intent", None) or (analysis.get("intent") if isinstance(analysis, dict) else None)
        routes = getattr(analysis, "routes", None) or (analysis.get("routes") if isinstance(analysis, dict) else None)
        if intent or routes:
            parts.append(f"\n路由：intent={intent} routes={routes}")
    return "\n".join(parts).strip()


def research_turn(state: AgentChatState, config: RunnableConfig) -> dict[str, Any]:
    question = _latest_human_text(list(state.get("messages") or []))
    if not question:
        return {
            "messages": [AIMessage(content="请输入要研究的问题（建议选 Serving 年报文档）。")],
        }

    doc_id = _resolve_doc_id(state, config)
    if not doc_id:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "未配置研究文档。请设置环境变量 AGENT_CHAT_DOC_ID，"
                        "或在 LangGraph configurable 中传入 doc_id，"
                        "或先跑 Serving→L3 生成 data/reports/serving_eval/*。"
                    )
                )
            ],
            "doc_id": None,
        }

    from app.api.dependencies import get_document_pipeline_service
    from app.core.db import build_company_id
    from app.workflows.orchestrator.graph import (
        AgentKind,
        classify_intent,
        format_multi_intent_note,
    )

    record = get_document_pipeline_service().get_document(doc_id)
    company_id = (
        build_company_id(record.metadata.company) if record.metadata.company else None
    )
    intent_plan = classify_intent({"question": question})
    agent_used: AgentKind = intent_plan.get("agent_used") or "research"
    sub_intents: list[AgentKind] = list(intent_plan.get("sub_intents") or [])
    secondary: AgentKind | None = intent_plan.get("secondary_intent")
    doc_id_b = _resolve_doc_id_b(state, config)

    content = _invoke_chat_specialist(
        agent_used=agent_used,
        question=question,
        doc_id=doc_id,
        doc_id_b=doc_id_b,
        company_id=company_id,
    )
    secondary_ran: AgentKind | None = None
    if secondary and secondary != agent_used:
        try:
            secondary_block = _invoke_chat_specialist(
                agent_used=secondary,
                question=question,
                doc_id=doc_id,
                doc_id_b=doc_id_b,
                company_id=company_id,
            )
            if secondary_block.strip():
                content = f"{content}\n\n——\n【次级 · {secondary}】\n{secondary_block}"
                secondary_ran = secondary
        except Exception:  # noqa: BLE001
            secondary_ran = None

    note = format_multi_intent_note(
        sub_intents,
        agent_used,
        secondary_ran=secondary_ran,
    )
    if note:
        content = f"{content}\n{note}"

    return {
        "messages": [AIMessage(content=content)],
        "doc_id": doc_id,
        "doc_id_b": doc_id_b,
    }


def build_agent_chat_graph():
    builder = StateGraph(AgentChatState)
    builder.add_node("research_turn", research_turn)
    builder.add_edge(START, "research_turn")
    builder.add_edge("research_turn", END)
    return builder.compile()


graph = build_agent_chat_graph()
