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


def _format_answer(preview: Any) -> str:
    answer = (getattr(preview, "answer", None) or "").strip()
    synthesis = getattr(preview, "synthesis", None)
    if synthesis is not None and getattr(synthesis, "answer", None):
        answer = str(synthesis.answer).strip() or answer
    metrics = getattr(preview, "metrics", None) or []
    warnings = getattr(preview, "warnings", None) or []
    parts = [answer or "（未生成文本答案；见下方证据摘要）"]
    if metrics:
        parts.append("\n结构化指标：")
        for item in metrics[:8]:
            if isinstance(item, dict):
                key = item.get("metric_key")
                period = item.get("period")
                value = item.get("value")
            else:
                key = getattr(item, "metric_key", None)
                period = getattr(item, "period", None)
                value = getattr(item, "value", None)
            parts.append(f"- {key} · {period} = {value}")
    if warnings:
        parts.append("\nWarnings：")
        for warning in warnings[:6]:
            parts.append(f"- {warning}")
    analysis = getattr(preview, "query_analysis", None)
    if analysis is not None:
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

    from app.api.dependencies import get_research_service

    preview = get_research_service().preview(doc_id=doc_id, question=question, top_k=5)
    return {
        "messages": [AIMessage(content=_format_answer(preview))],
        "doc_id": doc_id,
    }


def build_agent_chat_graph():
    builder = StateGraph(AgentChatState)
    builder.add_node("research_turn", research_turn)
    builder.add_edge(START, "research_turn")
    builder.add_edge("research_turn", END)
    return builder.compile()


graph = build_agent_chat_graph()
