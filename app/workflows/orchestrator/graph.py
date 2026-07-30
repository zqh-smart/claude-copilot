"""P6 multi-agent orchestrator — classify intent and delegate to specialist graphs."""

from __future__ import annotations

import re
from typing import Any, Callable, Literal, TypedDict

AgentKind = Literal["research", "risk", "quant", "structured"]

_RISK_ROUTE_CUES = ("风险", "暴露", "risk", "不确定性", "合规风险", "信用风险")
_GROWTH_CUES = ("growth", "trend", "cagr", "yoy", "增长", "同比", "趋势", "复合增长")
_METRIC_TERMS = (
    "revenue",
    "net income",
    "income",
    "profit",
    "assets",
    "liabilities",
    "equity",
    "cash flow",
    "eps",
    "营收",
    "营业收入",
    "收入",
    "利润",
    "净利润",
    "资产",
    "负债",
    "现金流",
    "每股收益",
)
_AMOUNT_CUES = ("多少", "是多少", "数额", "how much", "amount", "value", "数值", "金额")
_CAUSAL_CUES = ("为什么", "为何", "why", "原因", "缘故", "驱动", "due to", "because")
_CLAUSE_SPLIT = re.compile(
    r"(?:以及|还有|并且|同时|[；;]|\band\b|\balso\b)",
    flags=re.IGNORECASE,
)
_AGENT_PRIORITY: tuple[AgentKind, ...] = ("risk", "quant", "structured", "research")


class OrchestratorState(TypedDict, total=False):
    question: str
    doc_id: str
    company_id: str | None
    top_k: int
    agent_used: AgentKind
    sub_intents: list[AgentKind]
    answer: str
    warnings: list[str]


def _route_to_risk_agent(question: str) -> bool:
    """Same rules as agent_chat — risk cues unless metric-amount phrasing."""
    if not question.strip():
        return False
    if not any(cue in question.casefold() for cue in _RISK_ROUTE_CUES):
        return False
    if _is_metric_amount_question(question):
        return False
    return True


def _is_metric_amount_question(question: str) -> bool:
    normalized = question.casefold()
    if re.search(
        r"\d{4}\s*年.*(收入|营收|现金流|利润|revenue|net income).*(多少|是多少|数额)",
        question,
        flags=re.IGNORECASE,
    ):
        return True
    has_metric = any(term in normalized for term in _METRIC_TERMS)
    has_amount = any(cue in normalized for cue in _AMOUNT_CUES)
    has_year = bool(re.search(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", question))
    return has_metric and (has_amount or has_year)


def _route_to_quant_agent(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", question).strip().casefold()
    return any(cue in normalized for cue in _GROWTH_CUES)


def _split_question_clauses(question: str) -> list[str]:
    parts = [part.strip() for part in _CLAUSE_SPLIT.split(question.strip()) if part.strip()]
    return parts or [question.strip()]


def _clause_needs_research(clause: str) -> bool:
    normalized = clause.casefold()
    if not any(cue in normalized for cue in _CAUSAL_CUES):
        return False
    if _route_to_quant_agent(clause):
        return False
    return True


def _clause_intents(clause: str) -> set[AgentKind]:
    intents: set[AgentKind] = set()
    if _route_to_risk_agent(clause):
        intents.add("risk")
    if _route_to_quant_agent(clause):
        intents.add("quant")
    if _is_metric_amount_question(clause):
        intents.add("structured")
    if _clause_needs_research(clause):
        intents.add("research")
    return intents


def decompose_question(question: str) -> list[AgentKind]:
    """Lightweight multi-intent detection for logging and primary-agent selection."""
    normalized = question.strip()
    if not normalized:
        return ["research"]
    combined: set[AgentKind] = set()
    for clause in _split_question_clauses(normalized):
        combined |= _clause_intents(clause)
    if not combined:
        combined.add("research")
    return [agent for agent in _AGENT_PRIORITY if agent in combined]


def _resolve_primary_agent(sub_intents: list[AgentKind], question: str) -> AgentKind:
    primary: AgentKind = "research"
    for agent in _AGENT_PRIORITY:
        if agent in sub_intents:
            primary = agent
            break

    has_structured = "structured" in sub_intents
    has_quant = "quant" in sub_intents
    has_causal_research = "research" in sub_intents

    if has_structured and has_quant and primary == "structured":
        return "quant"
    if has_structured and has_causal_research and not has_quant and primary == "structured":
        return "research"
    return primary


def classify_intent(state: OrchestratorState) -> dict[str, Any]:
    question = str(state.get("question") or "").strip()
    sub_intents = decompose_question(question)
    agent_used = _resolve_primary_agent(sub_intents, question)
    return {"agent_used": agent_used, "sub_intents": sub_intents}


def _resolve_company_id(state: OrchestratorState) -> str | None:
    if state.get("company_id"):
        return str(state["company_id"])
    from app.api.dependencies import get_document_pipeline_service
    from app.core.db import build_company_id

    record = get_document_pipeline_service().get_document(state["doc_id"])
    if record.metadata.company:
        return build_company_id(record.metadata.company)
    return None


def _format_structured_answer(preview: Any) -> str:
    metrics = list(getattr(preview, "metrics", None) or [])
    parts = ["【结构化 · Structured Agent】"]
    if metrics:
        parts.append("检索到的结构化指标：")
        for item in metrics[:8]:
            if isinstance(item, dict):
                key = item.get("metric_key", "")
                period = item.get("period", "")
                value = item.get("value", "")
            else:
                key = getattr(item, "metric_key", "")
                period = getattr(item, "period", "")
                value = getattr(item, "value", "")
            parts.append(f"- {key} · {period} = {value}")
    answer = str(getattr(preview, "answer", None) or "").strip()
    if answer:
        parts.append(answer)
    elif not metrics:
        parts.append("未检索到匹配的结构化指标。")
    return "\n".join(parts).strip()


def _format_quant_answer(preview: Any) -> str:
    calculations = list(getattr(preview, "calculations", None) or [])
    parts = ["【量化 · Quant Agent】"]
    if calculations:
        parts.append("增长与同比计算：")
        for item in calculations[:6]:
            if isinstance(item, dict):
                metric_key = item.get("metric_key", "")
                cagr = item.get("cagr")
                yoy = item.get("yoy_growth") or {}
            else:
                metric_key = getattr(item, "metric_key", "")
                cagr = getattr(item, "cagr", None)
                yoy = getattr(item, "yoy_growth", None) or {}
            if cagr is not None:
                parts.append(f"- {metric_key} CAGR = {cagr:.2%}")
            for year, rate in sorted(yoy.items()):
                parts.append(f"- {metric_key} YoY {year} = {rate:.2%}")
    answer = str(getattr(preview, "answer", None) or "").strip()
    if answer:
        parts.append(answer)
    elif not calculations:
        parts.append("未生成增长计算；请确认问题含同比/CAGR/增长表述且文档含多期指标。")
    return "\n".join(parts).strip()


def _default_delegate_research(state: OrchestratorState) -> dict[str, Any]:
    from app.api.dependencies import get_research_service

    top_k = state.get("top_k") or 5
    preview = get_research_service().preview(
        doc_id=state["doc_id"],
        question=state["question"],
        top_k=top_k,
    )
    return {
        "agent_used": "research",
        "answer": str(getattr(preview, "answer", None) or "").strip(),
        "warnings": list(getattr(preview, "warnings", None) or []),
    }


def _default_delegate_risk(state: OrchestratorState) -> dict[str, Any]:
    from app.workflows.risk.graph import graph as risk_graph

    company_id = _resolve_company_id(state)
    result = risk_graph.invoke(
        {
            "doc_id": state["doc_id"],
            "company_id": company_id,
            "question": state["question"],
            "top_k": state.get("top_k") or 5,
        }
    )
    return {
        "agent_used": "risk",
        "answer": str(result.get("answer") or "").strip(),
        "warnings": list(result.get("warnings") or []),
    }


def _default_delegate_quant(state: OrchestratorState) -> dict[str, Any]:
    from app.workflows.quant.graph import graph as quant_graph

    company_id = _resolve_company_id(state)
    result = quant_graph.invoke(
        {
            "doc_id": state["doc_id"],
            "company_id": company_id,
            "question": state["question"],
            "top_k": state.get("top_k") or 5,
        }
    )
    return {
        "agent_used": "quant",
        "answer": str(result.get("answer") or "").strip(),
        "warnings": list(result.get("warnings") or []),
    }


def _default_delegate_structured(state: OrchestratorState) -> dict[str, Any]:
    from app.api.dependencies import get_research_service

    top_k = state.get("top_k") or 5
    preview = get_research_service().preview(
        doc_id=state["doc_id"],
        question=state["question"],
        top_k=top_k,
    )
    return {
        "agent_used": "structured",
        "answer": _format_structured_answer(preview),
        "warnings": list(getattr(preview, "warnings", None) or []),
    }


def _route_after_classify(state: OrchestratorState) -> str:
    return str(state.get("agent_used") or "research")


def build_orchestrator_graph(
    *,
    delegate_research: Callable[[OrchestratorState], dict[str, Any]] | None = None,
    delegate_risk: Callable[[OrchestratorState], dict[str, Any]] | None = None,
    delegate_quant: Callable[[OrchestratorState], dict[str, Any]] | None = None,
    delegate_structured: Callable[[OrchestratorState], dict[str, Any]] | None = None,
):
    research = delegate_research or _default_delegate_research
    risk = delegate_risk or _default_delegate_risk
    quant = delegate_quant or _default_delegate_quant
    structured = delegate_structured or _default_delegate_structured

    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return _FallbackOrchestratorGraph(
            classify_intent,
            research,
            risk,
            quant,
            structured,
        )

    builder = StateGraph(OrchestratorState)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("delegate_research", research)
    builder.add_node("delegate_risk", risk)
    builder.add_node("delegate_quant", quant)
    builder.add_node("delegate_structured", structured)
    builder.add_edge(START, "classify_intent")
    builder.add_conditional_edges(
        "classify_intent",
        _route_after_classify,
        {
            "research": "delegate_research",
            "risk": "delegate_risk",
            "quant": "delegate_quant",
            "structured": "delegate_structured",
        },
    )
    builder.add_edge("delegate_research", END)
    builder.add_edge("delegate_risk", END)
    builder.add_edge("delegate_quant", END)
    builder.add_edge("delegate_structured", END)
    return builder.compile()


class _FallbackOrchestratorGraph:
    def __init__(
        self,
        classify_fn: Callable[[OrchestratorState], dict[str, Any]],
        research_fn: Callable[[OrchestratorState], dict[str, Any]],
        risk_fn: Callable[[OrchestratorState], dict[str, Any]],
        quant_fn: Callable[[OrchestratorState], dict[str, Any]],
        structured_fn: Callable[[OrchestratorState], dict[str, Any]],
    ) -> None:
        self._classify_fn = classify_fn
        self._delegates = {
            "research": research_fn,
            "risk": risk_fn,
            "quant": quant_fn,
            "structured": structured_fn,
        }

    def invoke(self, state: dict) -> dict:
        updated = {**state, **self._classify_fn(state)}
        agent = str(updated.get("agent_used") or "research")
        delegate = self._delegates.get(agent, self._delegates["research"])
        return {**updated, **delegate(updated)}


graph = build_orchestrator_graph()
