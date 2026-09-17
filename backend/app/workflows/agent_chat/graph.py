"""Messages-compatible LangGraph agent for Agent Chat UI.

Exposes graph id ``agent`` via ``langgraph.json`` / ``langgraph dev`` (port 2024).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.config import get_settings
from src.claude_copilot.schemas.financial_data import FinancialMetricObservation
from src.claude_copilot.schemas.knowledge_graph import GraphPath
from src.claude_copilot.schemas.research import (
    ChatResearchResult,
    FusionSummary,
    GroundedCitation,
    GroundedSynthesis,
    MetricCalculation,
    ResearchHit,
    ResearchPreviewResponse,
)


class AgentChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    doc_id: str | None
    doc_id_b: str | None
    chat_memory_prepend: str | None
    chat_memory_warnings: list[str]
    chat_memory_session_id: str | None


def _latest_human_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = _human_message_text(message)
            if text:
                return text
    return ""


def _human_message_text(message: HumanMessage) -> str:
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


def _looks_like_follow_up(question: str) -> bool:
    """FinanceBench-style coreference: short follow-ups need the prior turn."""
    fold = question.strip().casefold()
    if not fold:
        return False
    if fold.endswith("呢") or fold.endswith("呢？") or fold.endswith("呢?"):
        return True
    return fold.startswith(("那", "还有", "以及", "再看", "what about", "how about", "and "))


def standalone_research_question(messages: list[AnyMessage]) -> str:
    """Rewrite '净利润呢？' against the previous user question before retrieve."""
    humans = [
        text
        for message in messages
        if isinstance(message, HumanMessage) and (text := _human_message_text(message))
    ]
    if not humans:
        return ""
    current = humans[-1]
    if len(humans) < 2 or not _looks_like_follow_up(current):
        return current
    previous = humans[-2]
    if previous == current:
        return current
    return f"{previous}\n{current}"


def _latest_ai_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
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
    paths = sorted(
        directory.glob("*_serving_eval.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
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
        prev_num = (
            prev[2] if isinstance(prev[2], (int, float)) and not isinstance(prev[2], bool) else None
        )
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
    if "doc_id_b" in lower or "未配置第二份" in warning or "未选择第二份" in warning:
        return "还未选择对比财报。请在顶部选择「对比财报」。"
    if "report_workflow 需要 doc_id" in warning:
        return "还未选择研究财报。请在顶部选择「研究财报」。"
    return warning


def _format_risk_answer(result: dict[str, Any]) -> str:
    answer = str(result.get("answer") or "").strip()
    findings = list(result.get("risk_findings") or [])
    parts = ["【风险】"]
    if answer:
        parts.append(answer)
    elif findings:
        parts.append(f"识别到 {len(findings)} 条 HAS_RISK 关联。")
    else:
        parts.append("未检索到图谱风险边；请确认文档已入库且含风险披露。")
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


def _hits_from_items(items: list[Any] | None) -> list[ResearchHit]:
    hits: list[ResearchHit] = []
    for item in items or []:
        if isinstance(item, ResearchHit):
            hits.append(item)
            continue
        payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        if not isinstance(payload, dict):
            continue
        segment_id = str(payload.get("segment_id") or "")
        content = str(payload.get("content") or "").strip()
        if not segment_id or not content:
            continue
        score = payload.get("score")
        hits.append(
            ResearchHit(
                segment_id=segment_id,
                score=float(score)
                if isinstance(score, (int, float)) and not isinstance(score, bool)
                else 0.0,
                content=content,
                metadata=dict(payload.get("metadata") or {}),
            )
        )
    return hits


def _metric_from_item(item: Any, *, default_doc_id: str) -> FinancialMetricObservation | None:
    payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
    if not isinstance(payload, dict):
        return None
    metric_key = str(payload.get("metric_key") or "")
    if not metric_key:
        return None
    value = payload.get("value")
    if value is None:
        return None
    period_year = payload.get("period_year")
    page_range = payload.get("page_range")
    typed_range: tuple[int, int] | None = None
    if isinstance(page_range, (list, tuple)) and len(page_range) == 2:
        start, end = page_range
        if isinstance(start, int) and isinstance(end, int):
            typed_range = (start, end)
    return FinancialMetricObservation(
        company_id=str(payload.get("company_id") or "unknown"),
        company=str(payload.get("company") or ""),
        document_id=str(payload.get("document_id") or default_doc_id),
        document_year=payload.get("document_year")
        if isinstance(payload.get("document_year"), int)
        else None,
        metric_key=metric_key,
        period=str(payload.get("period") or period_year or ""),
        period_year=period_year if isinstance(period_year, int) else None,
        value=value,
        statement_type=payload.get("statement_type")
        if isinstance(payload.get("statement_type"), str)
        else None,
        unit=payload.get("unit") if isinstance(payload.get("unit"), str) else None,
        currency=payload.get("currency") if isinstance(payload.get("currency"), str) else None,
        source_table_id=payload.get("source_table_id")
        if isinstance(payload.get("source_table_id"), str)
        else None,
        source_table_title=payload.get("source_table_title")
        if isinstance(payload.get("source_table_title"), str)
        else None,
        source_section=payload.get("source_section")
        if isinstance(payload.get("source_section"), str)
        else None,
        page_range=typed_range,
        provenance=dict(payload.get("provenance") or {}),
    )


def _metrics_from_items(
    items: list[Any] | None, *, default_doc_id: str
) -> list[FinancialMetricObservation]:
    metrics: list[FinancialMetricObservation] = []
    for item in items or []:
        metric = _metric_from_item(item, default_doc_id=default_doc_id)
        if metric is not None:
            metrics.append(metric)
    return metrics


def _metrics_from_calculations(
    calculations: list[Any] | None,
    *,
    default_doc_id: str,
    company_id: str | None,
) -> list[FinancialMetricObservation]:
    metrics: list[FinancialMetricObservation] = []
    for item in calculations or []:
        payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        if not isinstance(payload, dict):
            continue
        metric_key = str(payload.get("metric_key") or "")
        yearly = payload.get("yearly_values") or {}
        if not metric_key or not isinstance(yearly, dict):
            continue
        for year, value in yearly.items():
            if value is None:
                continue
            period_year = int(year) if str(year).isdigit() else None
            metrics.append(
                FinancialMetricObservation(
                    company_id=company_id or "unknown",
                    company="",
                    document_id=default_doc_id,
                    metric_key=metric_key,
                    period=str(year),
                    period_year=period_year,
                    value=value,
                )
            )
    return metrics


def _metrics_from_compare_matrix(
    matrix: list[Any] | None,
    *,
    doc_id_a: str,
    doc_id_b: str,
) -> list[FinancialMetricObservation]:
    metrics: list[FinancialMetricObservation] = []
    for row in matrix or []:
        if not isinstance(row, dict):
            continue
        metric_key = str(row.get("metric_key") or "")
        period = str(row.get("period") or "")
        if not metric_key:
            continue
        for value, doc_id in ((row.get("value_a"), doc_id_a), (row.get("value_b"), doc_id_b)):
            if value is None:
                continue
            metrics.append(
                FinancialMetricObservation(
                    company_id="unknown",
                    company="",
                    document_id=doc_id,
                    metric_key=metric_key,
                    period=period,
                    value=value,
                )
            )
    return metrics


def _hits_from_risk_findings(findings: list[Any] | None) -> list[ResearchHit]:
    hits: list[ResearchHit] = []
    for index, item in enumerate(findings or [], start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("evidence") or item.get("summary") or "").strip()
        risk_type = str(item.get("risk_type") or f"risk-{index}")
        if not content:
            content = risk_type
        hits.append(
            ResearchHit(
                segment_id=f"risk:{risk_type}:{index}",
                score=1.0,
                content=content,
                metadata={"risk_type": risk_type, "relation": item.get("relation")},
            )
        )
    return hits


def _hits_from_report_sections(sections: list[Any] | None) -> list[ResearchHit]:
    hits: list[ResearchHit] = []
    for index, section in enumerate(sections or [], start=1):
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or f"section-{index}")
        bullets = [
            str(item).strip() for item in (section.get("bullets") or []) if str(item).strip()
        ]
        content = "\n".join([title, *bullets]).strip()
        if not content:
            continue
        hits.append(
            ResearchHit(
                segment_id=f"report:{title}:{index}",
                score=1.0,
                content=content,
                metadata={"section_title": title},
            )
        )
    return hits


def _graph_paths_from_items(items: list[Any] | None) -> list[GraphPath]:
    paths: list[GraphPath] = []
    for item in items or []:
        try:
            paths.append(item if isinstance(item, GraphPath) else GraphPath.model_validate(item))
        except (TypeError, ValueError):
            continue
    return paths


def _calculations_from_items(items: list[Any] | None) -> list[MetricCalculation]:
    calculations: list[MetricCalculation] = []
    for item in items or []:
        try:
            calculations.append(
                item
                if isinstance(item, MetricCalculation)
                else MetricCalculation.model_validate(item)
            )
        except (TypeError, ValueError):
            continue
    return calculations


def _preview_from_evidence(
    *,
    doc_id: str,
    question: str,
    answer: str,
    hits: list[ResearchHit] | None = None,
    metrics: list[FinancialMetricObservation] | None = None,
    calculations: list[MetricCalculation] | None = None,
    graph_paths: list[GraphPath] | None = None,
    warnings: list[str] | None = None,
    fusion_summary: FusionSummary | None = None,
) -> ResearchPreviewResponse:
    evidence_hits = list(hits or [])
    evidence_metrics = list(metrics or [])
    citations = [
        GroundedCitation(evidence_id=f"V{index}", claim=hit.content[:120])
        for index, hit in enumerate(evidence_hits, start=1)
    ]
    citations.extend(
        GroundedCitation(
            evidence_id=f"S{index}",
            claim=f"{metric.metric_key} · {metric.period} = {metric.value}",
        )
        for index, metric in enumerate(evidence_metrics[:30], start=1)
    )
    evidence_paths = list(graph_paths or [])
    citations.extend(
        GroundedCitation(evidence_id=f"G{index}", claim=path.summary[:120])
        for index, path in enumerate(evidence_paths[:8], start=1)
    )
    grounded = bool(evidence_hits or evidence_metrics or evidence_paths)
    markers = [citation.evidence_id for citation in citations]
    if markers and not any(f"[{marker}]" in answer for marker in markers):
        answer = f"{answer.rstrip()}\n\n" + " ".join(f"[{marker}]" for marker in markers)
    return ResearchPreviewResponse(
        doc_id=doc_id,
        question=question,
        answer=answer,
        hits=evidence_hits,
        metrics=evidence_metrics,
        calculations=list(calculations or []),
        graph_paths=list(graph_paths or []),
        fusion_summary=fusion_summary,
        warnings=[_humanize_warning(str(item)) for item in (warnings or []) if item],
        synthesis=GroundedSynthesis(
            answer=answer,
            citations=citations,
            confidence=1.0 if grounded else 0.0,
        )
        if citations
        else None,
        grounded=grounded,
    )


def _invoke_chat_specialist(
    *,
    agent_used: str,
    question: str,
    doc_id: str,
    doc_id_b: str | None,
    company_id: str | None,
    chat_memory_context: str | None = None,
) -> str | ResearchPreviewResponse:
    """Run one specialist for agent chat; shared by primary and secondary intents.

    ``question`` must stay clean for retrieval/intent. ``chat_memory_context`` is
    only forwarded into research synthesis (not Qdrant/SQL/graph queries).
    """
    from app.api.dependencies import get_research_service

    if agent_used == "risk":
        from app.workflows.risk.graph import graph as risk_graph

        result = risk_graph.invoke(
            {
                "doc_id": doc_id,
                "company_id": company_id,
                "question": question,
                "top_k": 5,
            }
        )
        hits = _hits_from_items(result.get("hits"))
        if not hits:
            hits = _hits_from_risk_findings(result.get("risk_findings"))
        finding_highlights = [
            str(item.get("summary") or item.get("risk_type") or "").strip()
            for item in (result.get("risk_findings") or [])
            if isinstance(item, dict)
            and str(item.get("summary") or item.get("risk_type") or "").strip()
        ]
        fusion = None
        if finding_highlights:
            fusion = FusionSummary(
                query_intent="risk",
                routes=["graph"],
                graph_path_count=len(result.get("graph_paths") or []),
                highlights=finding_highlights[:6],
                summary="风险要点：" + "；".join(finding_highlights[:3]),
            )
        return _preview_from_evidence(
            doc_id=doc_id,
            question=question,
            answer=_format_risk_answer(result),
            hits=hits,
            graph_paths=_graph_paths_from_items(result.get("graph_paths")),
            warnings=list(result.get("warnings") or []),
            fusion_summary=fusion,
        )
    if agent_used == "compare":
        from app.workflows.comparison_workflow.graph import graph as comparison_workflow

        if not doc_id_b:
            return _preview_from_evidence(
                doc_id=doc_id,
                question=question,
                answer=("【对比】未选择第二份文档。请在顶部选择「对比财报」。"),
                warnings=["未配置第二份文档 doc_id_b"],
            )
        result = comparison_workflow.invoke(
            {
                "doc_id_a": doc_id,
                "doc_id_b": doc_id_b,
                "question": question,
            }
        )
        metrics = _metrics_from_compare_matrix(
            result.get("compare_matrix"),
            doc_id_a=doc_id,
            doc_id_b=doc_id_b,
        )
        highlights = [
            str(item).strip()
            for item in (result.get("compare_highlights") or [])
            if str(item).strip()
        ]
        fusion = None
        if highlights:
            fusion = FusionSummary(
                query_intent="compare",
                routes=["sql"],
                metric_count=len(metrics),
                highlights=highlights[:6],
                summary="对比要点：" + "；".join(highlights[:3]),
            )
        return _preview_from_evidence(
            doc_id=doc_id,
            question=question,
            answer=str(result.get("answer") or "").strip() or "【对比】未生成对比结果。",
            metrics=metrics,
            warnings=list(result.get("warnings") or []),
            fusion_summary=fusion,
        )
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
        content = f"【量化】\n{answer}" if answer else "【量化】未生成计算结果。"
        warnings = [str(item) for item in (quant_result.get("warnings") or [])]
        if warnings:
            content += "\n说明：\n" + "\n".join(f"- {_humanize_warning(w)}" for w in warnings[:4])
        metrics = _metrics_from_items(quant_result.get("metrics"), default_doc_id=doc_id)
        if not metrics:
            metrics = _metrics_from_calculations(
                quant_result.get("calculations"),
                default_doc_id=doc_id,
                company_id=company_id,
            )
        calc_highlights: list[str] = []
        for item in quant_result.get("calculations") or []:
            payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            if not isinstance(payload, dict):
                continue
            metric_key = str(payload.get("metric_key") or "").strip()
            if not metric_key:
                continue
            bits: list[str] = []
            yoy = payload.get("yoy_growth") or {}
            if isinstance(yoy, dict) and yoy:
                year, rate = sorted(yoy.items())[-1]
                bits.append(f"YoY {year}={float(rate) * 100:.2f}%")
            cagr = payload.get("cagr")
            if cagr is not None:
                bits.append(f"CAGR={float(cagr) * 100:.2f}%")
            calc_highlights.append(f"{metric_key}：" + ("；".join(bits) if bits else "有多期数据"))
        if not calc_highlights:
            calc_highlights = [
                f"{metric.metric_key} · {metric.period} = {metric.value}" for metric in metrics[:6]
            ]
        fusion = None
        if calc_highlights:
            fusion = FusionSummary(
                query_intent="quant",
                routes=["sql"],
                metric_count=len(metrics),
                highlights=calc_highlights[:6],
                summary="量化要点：" + "；".join(calc_highlights[:3]),
            )
        return _preview_from_evidence(
            doc_id=doc_id,
            question=question,
            answer=content,
            metrics=metrics,
            calculations=_calculations_from_items(quant_result.get("calculations")),
            warnings=warnings,
            fusion_summary=fusion,
        )
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
        metrics = _metrics_from_items(report_result.get("metrics"), default_doc_id=doc_id)
        if not metrics:
            metrics = _metrics_from_calculations(
                report_result.get("calculations"),
                default_doc_id=doc_id,
                company_id=company_id,
            )
        section_titles = [
            str(section.get("title") or "").strip()
            for section in (report_result.get("report_sections") or [])
            if isinstance(section, dict) and str(section.get("title") or "").strip()
        ]
        fusion = None
        if section_titles:
            fusion = FusionSummary(
                query_intent="report",
                routes=["sql"],
                metric_count=len(metrics),
                highlights=section_titles[:6],
                summary="提纲章节：" + "；".join(section_titles[:3]),
            )
        return _preview_from_evidence(
            doc_id=doc_id,
            question=question,
            answer=str(report_result.get("answer") or "").strip() or "【报告提纲】未生成提纲。",
            hits=_hits_from_report_sections(report_result.get("report_sections")),
            metrics=metrics,
            calculations=_calculations_from_items(report_result.get("calculations")),
            warnings=list(report_result.get("warnings") or []),
            fusion_summary=fusion,
        )

    preview = get_research_service().preview(
        doc_id=doc_id,
        question=question,
        top_k=5,
        chat_memory_context=chat_memory_context,
    )
    return preview


def _specialist_answer(result: str | ResearchPreviewResponse, agent_used: str) -> str:
    if isinstance(result, str):
        return result
    if agent_used in {"research", "structured"}:
        content = _format_answer(result)
        if agent_used == "structured":
            content = f"【结构化】\n{content}"
        return content
    return result.answer


_ROUTE_LABELS = {"vector": "语义", "sql": "结构化", "graph": "图谱"}
_INTENT_LABELS = {
    "semantic": "语义检索",
    "structured": "结构化查询",
    "relational": "关系查询",
    "hybrid": "混合检索",
    "compare": "对比分析",
    "report": "报告提纲",
    "risk": "风险分析",
    "quant": "增长量化",
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
    intent_label = _INTENT_LABELS.get(intent) or "检索"
    parts.append(f"\n{intent_label}摘要：")
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
        ("502" in item)
        or ("timed out" in item.lower())
        or ("timeout" in item.lower())
        or ("grounded synthesis failed" in item.lower())
        for item in warnings
    )
    primary = _prefer_primary_metrics(_metric_rows(list(metrics)))

    if synthesis_answer and not llm_failed:
        lead = synthesis_answer
    elif primary:
        key, period, value = primary[0]
        lead = (
            f"{period}年{key}为 {value}。" if period.isdigit() else f"{key}（{period}）为 {value}。"
        )
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
        intent = getattr(analysis, "intent", None) or (
            analysis.get("intent") if isinstance(analysis, dict) else None
        )
        routes = getattr(analysis, "routes", None) or (
            analysis.get("routes") if isinstance(analysis, dict) else None
        )
        labeled_routes = [_ROUTE_LABELS.get(str(route), str(route)) for route in (routes or [])]
        intent_text = _INTENT_LABELS.get(str(intent), "") if intent else ""
        if labeled_routes:
            parts.append(f"\n检索通道：{intent_text or '混合检索'}（{' · '.join(labeled_routes)}）")
        elif intent_text:
            parts.append(f"\n检索通道：{intent_text}")
    return "\n".join(parts).strip()


def recall_chat_memory(state: AgentChatState, config: RunnableConfig) -> dict[str, Any]:
    """Prefetch Chat memory from MemoryCore; never blocks the main turn."""
    from app.api.dependencies import get_chat_memory_client
    from app.core.chat_memory.ids import resolve_session_id

    question = _latest_human_text(list(state.get("messages") or []))
    session_id = resolve_session_id(config)
    if not question:
        return {
            "chat_memory_prepend": None,
            "chat_memory_warnings": [],
            "chat_memory_session_id": session_id,
        }
    bundle = get_chat_memory_client().recall(query=question, session_id=session_id)
    return {
        "chat_memory_prepend": bundle.context_text or None,
        "chat_memory_warnings": list(bundle.warnings),
        "chat_memory_session_id": session_id,
    }


def research_turn(state: AgentChatState, config: RunnableConfig) -> dict[str, Any]:
    messages = list(state.get("messages") or [])
    question = standalone_research_question(messages)
    if not question:
        return {
            "messages": [AIMessage(content="请输入要研究的问题（建议先选「研究财报」）。")],
        }

    doc_id = _resolve_doc_id(state, config)
    if not doc_id:
        return {
            "messages": [
                AIMessage(
                    content="未选择研究文档。请在顶部选择「研究财报」。",
                )
            ],
            "doc_id": None,
        }

    from app.api.dependencies import get_document_pipeline_service
    from app.core.db import build_company_id
    from app.workflows.orchestrator.graph import (
        _AGENT_LABELS,
        AgentKind,
        classify_intent,
        format_multi_intent_note,
    )

    record = get_document_pipeline_service().get_document(doc_id)
    company_id = build_company_id(record.metadata.company) if record.metadata.company else None
    intent_plan = classify_intent({"question": question})
    agent_used: AgentKind = intent_plan.get("agent_used") or "research"
    sub_intents: list[AgentKind] = list(intent_plan.get("sub_intents") or [])
    secondary: AgentKind | None = intent_plan.get("secondary_intent")
    doc_id_b = _resolve_doc_id_b(state, config)
    chat_memory_context = (state.get("chat_memory_prepend") or "").strip() or None

    primary_result = _invoke_chat_specialist(
        agent_used=agent_used,
        question=question,
        doc_id=doc_id,
        doc_id_b=doc_id_b,
        company_id=company_id,
        chat_memory_context=chat_memory_context,
    )
    content = _specialist_answer(primary_result, agent_used)
    previews = [primary_result] if isinstance(primary_result, ResearchPreviewResponse) else []
    secondary_ran: AgentKind | None = None
    if secondary and secondary != agent_used:
        try:
            secondary_result = _invoke_chat_specialist(
                agent_used=secondary,
                question=question,
                doc_id=doc_id,
                doc_id_b=doc_id_b,
                company_id=company_id,
                chat_memory_context=chat_memory_context,
            )
            secondary_block = _specialist_answer(secondary_result, secondary)
            if secondary_block.strip():
                if isinstance(secondary_result, ResearchPreviewResponse):
                    previews.append(secondary_result)
                label = _AGENT_LABELS.get(secondary, secondary)
                content = f"{content}\n\n——\n【次级 · {label}】\n{secondary_block}"
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

    request_message_id = next(
        (
            message.id
            for message in reversed(state.get("messages") or [])
            if isinstance(message, HumanMessage)
        ),
        None,
    )
    configurable = (config or {}).get("configurable") or {}
    snapshot = ChatResearchResult(
        thread_id=configurable.get("thread_id"),
        request_message_id=request_message_id,
        previews=previews,
    )
    return {
        "messages": [
            AIMessage(
                id=str(uuid4()),
                content=content,
                additional_kwargs={"research_result": snapshot.model_dump(mode="json")},
            )
        ],
        "doc_id": doc_id,
        "doc_id_b": doc_id_b,
    }


def capture_chat_memory(state: AgentChatState, config: RunnableConfig) -> dict[str, Any]:
    """Write the latest clean user/assistant turn to MemoryCore L0."""
    from app.api.dependencies import get_chat_memory_client
    from app.core.chat_memory.ids import resolve_session_id

    messages = list(state.get("messages") or [])
    user_text = _latest_human_text(messages)
    assistant_text = _latest_ai_text(messages)
    session_id = state.get("chat_memory_session_id") or resolve_session_id(config)
    if user_text and assistant_text:
        get_chat_memory_client().capture(
            session_id=session_id,
            user_text=user_text,
            assistant_text=assistant_text,
            metadata={
                "doc_id": state.get("doc_id"),
                "doc_id_b": state.get("doc_id_b"),
            },
        )
    return {}


def build_agent_chat_graph():
    builder = StateGraph(AgentChatState)
    builder.add_node("recall_chat_memory", recall_chat_memory)
    builder.add_node("research_turn", research_turn)
    builder.add_node("capture_chat_memory", capture_chat_memory)
    builder.add_edge(START, "recall_chat_memory")
    builder.add_edge("recall_chat_memory", "research_turn")
    builder.add_edge("research_turn", "capture_chat_memory")
    builder.add_edge("capture_chat_memory", END)
    return builder.compile()


graph = build_agent_chat_graph()
