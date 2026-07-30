"""LangGraph Risk Agent — graph + vector evidence, rule-based summary (LLM optional later)."""

from __future__ import annotations

from typing import Any, Callable, TypedDict


class RiskState(TypedDict, total=False):
    doc_id: str
    company_id: str | None
    question: str
    top_k: int
    hits: list[dict]
    graph_paths: list[dict]
    risk_findings: list[dict]
    warnings: list[str]
    answer: str


class _FallbackRiskGraph:
    def __init__(
        self,
        retrieve_fn: Callable[[dict], dict],
        summarize_fn: Callable[[dict], dict],
    ) -> None:
        self._retrieve_fn = retrieve_fn
        self._summarize_fn = summarize_fn

    def invoke(self, state: dict) -> dict:
        updated = {**state, **self._retrieve_fn(state)}
        return {**updated, **self._summarize_fn(updated)}


def _graph_path_to_dict(path: Any) -> dict:
    if hasattr(path, "model_dump"):
        return path.model_dump(mode="json")
    return dict(path)


def _extract_has_risk_findings(graph_paths: list[dict]) -> list[dict]:
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for path in graph_paths:
        nodes = path.get("nodes") or []
        node_by_id = {
            node.get("node_id"): node
            for node in nodes
            if isinstance(node, dict) and node.get("node_id")
        }
        for relationship in path.get("relationships") or []:
            if not isinstance(relationship, dict):
                continue
            if relationship.get("relationship_type") != "HAS_RISK":
                continue
            target_id = relationship.get("target_node_id")
            target = node_by_id.get(target_id) or {}
            risk_name = str(target.get("name") or target_id or "unknown_risk")
            key = (risk_name, str(relationship.get("relationship_id") or path.get("path_id") or ""))
            if key in seen:
                continue
            seen.add(key)
            properties = target.get("properties") or {}
            findings.append(
                {
                    "risk_type": risk_name,
                    "severity": properties.get("severity") or properties.get("risk_type") or "unknown",
                    "summary": path.get("summary") or risk_name,
                    "evidence": (relationship.get("evidence_text") or "")[:500],
                    "relation": "HAS_RISK",
                }
            )
    return findings


def _default_retrieve_risk(state: dict) -> dict:
    from app.api.dependencies import get_document_pipeline_service
    from app.core.db import build_company_id
    from app.api.dependencies import get_research_service

    doc_id = state["doc_id"]
    question = state["question"]
    top_k = state.get("top_k") or 5
    record = get_document_pipeline_service().get_document(doc_id)
    company_id = state.get("company_id") or (
        build_company_id(record.metadata.company) if record.metadata.company else None
    )
    preview = get_research_service().preview(doc_id=doc_id, question=question, top_k=top_k)
    graph_paths = [_graph_path_to_dict(item) for item in (preview.graph_paths or [])]
    hits = [
        {
            "segment_id": hit.segment_id,
            "score": hit.score,
            "content": hit.content,
            "metadata": dict(hit.metadata or {}),
        }
        for hit in (preview.hits or [])
    ]
    return {
        "company_id": company_id,
        "graph_paths": graph_paths,
        "hits": hits,
        "warnings": list(preview.warnings or []),
    }


def _default_summarize_risk(state: dict) -> dict:
    graph_paths = list(state.get("graph_paths") or [])
    hits = list(state.get("hits") or [])
    warnings = list(state.get("warnings") or [])
    findings = _extract_has_risk_findings(graph_paths)

    parts: list[str] = []
    if findings:
        parts.append(f"图谱识别到 {len(findings)} 条 HAS_RISK 风险关联：")
        for index, item in enumerate(findings[:8], start=1):
            parts.append(
                f"{index}. [{item['risk_type']}] {item['summary']}"
            )
    else:
        parts.append("未在图谱中命中 HAS_RISK 关系；以下为语义检索片段供参考。")

    risk_hits = [
        hit
        for hit in hits
        if any(
            cue in (hit.get("content") or "")
            for cue in ("风险", "risk", "暴露", "不确定性")
        )
    ]
    snippet_source = risk_hits or hits
    if snippet_source:
        parts.append("\n相关披露片段：")
        for hit in snippet_source[:3]:
            content = str(hit.get("content") or "").strip()
            if content:
                parts.append(f"- {content[:220]}{'…' if len(content) > 220 else ''}")

    if warnings:
        parts.append("\n说明：")
        for warning in warnings[:4]:
            parts.append(f"- {warning}")

    return {
        "risk_findings": findings,
        "answer": "\n".join(parts).strip(),
    }


def build_risk_graph(
    retrieve_fn: Callable[[dict], dict] | None = None,
    summarize_fn: Callable[[dict], dict] | None = None,
):
    retrieve = retrieve_fn or _default_retrieve_risk
    summarize = summarize_fn or _default_summarize_risk
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return _FallbackRiskGraph(retrieve, summarize)

    builder = StateGraph(RiskState)
    builder.add_node("retrieve_risk", retrieve)
    builder.add_node("summarize_risk", summarize)
    builder.add_edge(START, "retrieve_risk")
    builder.add_edge("retrieve_risk", "summarize_risk")
    builder.add_edge("summarize_risk", END)
    return builder.compile()


graph = build_risk_graph()
