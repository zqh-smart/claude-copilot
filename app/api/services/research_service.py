from app.core.db import build_company_id
from app.core.llm import GroundedResearchEngine
from app.core.prompts import RESEARCH_SYSTEM_PROMPT
from app.core.rag import LocalRetriever, RetrievalOrchestrator
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService
from app.workflows.research.graph import build_research_graph
from src.claude_copilot.schemas.research import (
    CriticIssue,
    CriticReview,
    GroundedSynthesis,
    MetricCalculation,
    QueryAnalysis,
    ResearchHit,
    ResearchPreviewResponse,
)


class ResearchService:
    def __init__(
        self,
        *,
        document_pipeline_service: DocumentPipelineService,
        retriever: LocalRetriever,
        orchestrator: RetrievalOrchestrator | None = None,
        grounded_engine: GroundedResearchEngine | None = None,
        max_revisions: int = 1,
    ) -> None:
        self._document_pipeline_service = document_pipeline_service
        self._retriever = retriever
        self._orchestrator = orchestrator
        self._grounded_engine = grounded_engine
        self._max_revisions = max(0, max_revisions)
        self._graph = build_research_graph(
            self._run_retrieval,
            self._synthesize_answer,
            self._critique_answer,
            self._revise_answer,
        )

    def preview(self, *, doc_id: str, question: str, top_k: int) -> ResearchPreviewResponse:
        record = self._document_pipeline_service.get_document(doc_id)
        company_id = (
            build_company_id(record.metadata.company)
            if record.metadata.company
            else None
        )
        result = self._graph.invoke(
            {
                "doc_id": doc_id,
                "company_id": company_id,
                "question": question,
                "top_k": top_k,
                "revision_count": 0,
                "max_revisions": (
                    self._max_revisions if self._grounded_engine is not None else 0
                ),
            }
        )
        return ResearchPreviewResponse(
            doc_id=doc_id,
            question=question,
            answer=result["answer"],
            hits=[ResearchHit.model_validate(hit) for hit in result["hits"]],
            query_analysis=QueryAnalysis.model_validate(result["query_analysis"]),
            metrics=result.get("metrics", []),
            calculations=[
                MetricCalculation.model_validate(item)
                for item in result.get("calculations", [])
            ],
            graph_paths=result.get("graph_paths", []),
            warnings=result.get("warnings", []),
            synthesis=GroundedSynthesis.model_validate(result["synthesis"]),
            critic=CriticReview.model_validate(result["critic"]),
            revision_count=result.get("revision_count", 0),
            grounded=result.get("grounded", False),
        )

    def _run_retrieval(self, state: dict) -> dict:
        if self._orchestrator is not None:
            result = self._orchestrator.retrieve(
                state["question"],
                doc_id=state["doc_id"],
                company_id=state.get("company_id"),
                top_k=state["top_k"],
            )
            return {
                "hits": [
                    {
                        "segment_id": segment.segment_id,
                        "score": round(score, 4),
                        "content": segment.content,
                    }
                    for segment, score in result.vector_hits
                ],
                "query_analysis": result.analysis.model_dump(mode="json"),
                "metrics": [
                    item.model_dump(mode="json") for item in result.metrics
                ],
                "calculations": [
                    item.model_dump(mode="json") for item in result.calculations
                ],
                "graph_paths": [
                    item.model_dump(mode="json") for item in result.graph_paths
                ],
                "warnings": result.warnings,
            }

        hits = self._retriever.retrieve(
            state["question"],
            doc_id=state["doc_id"],
            top_k=state["top_k"],
        )
        return {
            "hits": [
                {
                    "segment_id": segment.segment_id,
                    "score": round(score, 4),
                    "content": segment.content,
                }
                for segment, score in hits
            ],
            "query_analysis": QueryAnalysis(
                intent="semantic",
                routes=["vector"],
            ).model_dump(mode="json"),
            "metrics": [],
            "calculations": [],
            "graph_paths": [],
            "warnings": [],
        }

    def _synthesize_answer(self, state: dict) -> dict:
        if self._grounded_engine is None:
            synthesis = self._fallback_synthesis(state)
            return {
                "evidence": [],
                "synthesis": synthesis.model_dump(mode="json"),
                "answer": synthesis.answer,
            }

        evidence = self._grounded_engine.build_evidence(state)
        try:
            synthesis = self._grounded_engine.synthesize(
                question=state["question"],
                evidence=evidence,
            )
            return {
                "evidence": evidence,
                "synthesis": synthesis.model_dump(mode="json"),
                "answer": synthesis.answer,
            }
        except Exception as exc:
            synthesis = self._fallback_synthesis(
                state,
                limitation=f"LLM synthesis failed: {type(exc).__name__}",
            )
            return {
                "evidence": evidence,
                "synthesis": synthesis.model_dump(mode="json"),
                "answer": synthesis.answer,
                "warnings": [
                    *state.get("warnings", []),
                    f"grounded synthesis failed: {exc}",
                ],
                "revision_count": state.get("max_revisions", 0),
            }

    def _critique_answer(self, state: dict) -> dict:
        synthesis = GroundedSynthesis.model_validate(state["synthesis"])
        if self._grounded_engine is None:
            review = CriticReview(
                passed=False,
                score=0.0,
                issues=[
                    CriticIssue(
                        category="missing_evidence",
                        severity="high",
                        message="Formal LLM critic is not configured.",
                    )
                ],
                summary="Deterministic preview only; critic was not run.",
            )
            return {
                "critic": review.model_dump(mode="json"),
                "grounded": False,
            }

        try:
            review = self._grounded_engine.critique(
                question=state["question"],
                evidence=state.get("evidence", []),
                synthesis=synthesis,
            )
            return {
                "critic": review.model_dump(mode="json"),
                "grounded": review.passed,
            }
        except Exception as exc:
            review = CriticReview(
                passed=False,
                score=0.0,
                issues=[
                    CriticIssue(
                        category="logic_error",
                        severity="high",
                        message=f"Critic execution failed: {type(exc).__name__}",
                    )
                ],
                summary="Critic failed; answer cannot be marked grounded.",
            )
            return {
                "critic": review.model_dump(mode="json"),
                "grounded": False,
                "warnings": [
                    *state.get("warnings", []),
                    f"critic failed: {exc}",
                ],
                "revision_count": state.get("max_revisions", 0),
            }

    def _revise_answer(self, state: dict) -> dict:
        if self._grounded_engine is None:
            return {"revision_count": state.get("max_revisions", 0)}
        try:
            synthesis = self._grounded_engine.synthesize(
                question=state["question"],
                evidence=state.get("evidence", []),
                previous_draft=GroundedSynthesis.model_validate(state["synthesis"]),
                critic_review=CriticReview.model_validate(state["critic"]),
            )
            return {
                "synthesis": synthesis.model_dump(mode="json"),
                "answer": synthesis.answer,
                "revision_count": state.get("revision_count", 0) + 1,
            }
        except Exception as exc:
            return {
                "warnings": [
                    *state.get("warnings", []),
                    f"revision failed: {exc}",
                ],
                "revision_count": state.get("max_revisions", 0),
            }

    def _fallback_synthesis(
        self,
        state: dict,
        *,
        limitation: str = "Formal LLM grounded synthesis is not configured.",
    ) -> GroundedSynthesis:
        evidence_parts = []
        if state.get("metrics"):
            evidence_parts.append(
                "；".join(
                    (
                        f"{item['metric_key']}({item['period']})="
                        f"{item['value']} {item.get('unit') or ''} "
                        f"{item.get('currency') or ''}"
                    ).strip()
                    for item in state["metrics"][:10]
                )
            )
        if state.get("hits"):
            evidence_parts.extend(
                item["content"][:180] for item in state["hits"][:3]
            )
        if state.get("graph_paths"):
            evidence_parts.extend(
                item["summary"] for item in state["graph_paths"][:5]
            )
        if not evidence_parts:
            answer = (
                f"{RESEARCH_SYSTEM_PROMPT}\n\n"
                "当前没有检索到足够的文本或结构化证据，无法生成可靠回答。"
            )
        else:
            answer = "\n\n".join(evidence_parts)
        return GroundedSynthesis(
            answer=answer,
            key_findings=[],
            citations=[],
            confidence=0.25,
            limitations=[limitation],
        )
