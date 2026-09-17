"""Multi-subtask retrieval for report workflow (task decomposition)."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.rag.research_planner import is_deep_research_question, plan_deep_research


def collect_deep_report_evidence(state: dict) -> dict:
    settings = get_settings()
    if not settings.research_deep_retrieval_enabled:
        return {}
    question = str(state.get("question") or "")
    if not is_deep_research_question(question):
        return {}

    from app.api import dependencies
    from app.core.rag.orchestrator import QueryAnalyzer
    from src.claude_copilot.schemas.research import QueryAnalysis

    orchestrator = dependencies.get_research_service().orchestrator
    if orchestrator is None:
        return {"warnings": ["Deep report retrieval skipped: orchestrator unavailable."]}

    doc_id = state.get("doc_id")
    company_id = state.get("company_id")
    top_k = int(state.get("top_k") or 3)
    analyzer = QueryAnalyzer()
    base_analysis = analyzer.analyze(question)

    hits: list[dict] = []
    metrics: list[dict] = []
    graph_paths: list[dict] = []
    warnings: list[str] = []
    subtasks = []

    for task in plan_deep_research(question):
        subtasks.append(task.task_id)
        override = QueryAnalysis(
            intent=base_analysis.intent,
            routes=list(base_analysis.routes),
            metric_keys=task.metric_keys or list(base_analysis.metric_keys),
            years=list(base_analysis.years),
            needs_growth=base_analysis.needs_growth,
            section_hints=task.section_hints or list(base_analysis.section_hints),
            entity_scope=base_analysis.entity_scope,
        )
        result = orchestrator.retrieve(
            task.question,
            doc_id=doc_id,
            company_id=company_id,
            top_k=top_k,
            analysis_override=override,
        )
        for segment, score in result.vector_hits:
            hit = {
                "segment_id": segment.segment_id,
                "score": score,
                "content": segment.content,
                "metadata": dict(segment.metadata or {}),
            }
            if any(existing.get("segment_id") == hit["segment_id"] for existing in hits):
                continue
            hits.append(hit)
            if len(hits) >= top_k * 4:
                break
        metrics.extend(item.model_dump(mode="json") for item in result.metrics)
        graph_paths.extend(item.model_dump(mode="json") for item in result.graph_paths)
        warnings.extend(result.warnings)

    return {
        "research_subtasks": subtasks,
        "hits": hits[: top_k * 4],
        "metrics": metrics[:30],
        "graph_paths": graph_paths[: top_k * 2],
        "warnings": [
            *list(state.get("warnings") or []),
            f"Deep report retrieval executed {len(subtasks)} subtasks.",
            *warnings,
        ],
    }
