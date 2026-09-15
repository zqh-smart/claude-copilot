import re

from app.core.db import build_company_id
from app.core.llm import GroundedResearchEngine
from app.core.observability import Observability
from app.core.rag import LocalRetriever
from app.core.rag.orchestrator import (
    OrchestratedRetrievalResult,
    RetrievalOrchestrator,
)
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService
from app.workflows.research.graph import build_research_graph
from src.claude_copilot.schemas.research import (
    CriticIssue,
    CriticReview,
    FusionSummary,
    GroundedCitation,
    GroundedSynthesis,
    MetricCalculation,
    QueryAnalysis,
    ResearchHit,
    ResearchPreviewResponse,
    RetrievalPassDiagnostic,
    SecondRetrievalPlan,
)


class ResearchService:
    def __init__(
        self,
        *,
        document_pipeline_service: DocumentPipelineService,
        retriever: LocalRetriever,
        orchestrator: RetrievalOrchestrator | None = None,
        grounded_engine: GroundedResearchEngine | None = None,
        observability: Observability | None = None,
        capture_trace_content: bool = False,
        max_revisions: int = 1,
    ) -> None:
        self._document_pipeline_service = document_pipeline_service
        self._retriever = retriever
        self._orchestrator = orchestrator
        self._grounded_engine = grounded_engine
        self._observability = observability or Observability()
        self._capture_trace_content = capture_trace_content
        self._max_revisions = max(0, max_revisions)
        self._graph = build_research_graph(
            self._run_retrieval,
            self._synthesize_answer,
            self._critique_answer,
            self._revise_answer,
        )

    @property
    def orchestrator(self) -> RetrievalOrchestrator | None:
        return self._orchestrator

    def preview(
        self,
        *,
        doc_id: str,
        question: str,
        top_k: int,
        chat_memory_context: str | None = None,
    ) -> ResearchPreviewResponse:
        inputs = {"doc_id": doc_id, "top_k": top_k, "question_length": len(question)}
        if self._capture_trace_content:
            inputs["question"] = question
        if chat_memory_context:
            inputs["chat_memory_context_length"] = len(chat_memory_context)
        with self._observability.trace(
            "research.preview",
            inputs=inputs,
            metadata={"service": "ResearchService"},
        ) as span:
            response = self._preview(
                doc_id=doc_id,
                question=question,
                top_k=top_k,
                chat_memory_context=chat_memory_context,
            )
            span.set_output(
                {
                    "grounded": response.grounded,
                    "hit_count": len(response.hits),
                    "warning_count": len(response.warnings),
                    "revision_count": response.revision_count,
                }
            )
            return response

    def _preview(
        self,
        *,
        doc_id: str,
        question: str,
        top_k: int,
        chat_memory_context: str | None = None,
    ) -> ResearchPreviewResponse:
        record = self._document_pipeline_service.get_document(doc_id)
        company_id = (
            build_company_id(record.metadata.company)
            if record.metadata.company
            else None
        )
        memory = (chat_memory_context or "").strip()
        synthesis_question = (
            f"{memory}\n\n用户问题：{question}" if memory else question
        )
        result = self._graph.invoke(
            {
                "doc_id": doc_id,
                "company_id": company_id,
                "question": question,
                "synthesis_question": synthesis_question,
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
            fusion_summary=(
                FusionSummary.model_validate(result["fusion_summary"])
                if result.get("fusion_summary")
                else None
            ),
            warnings=result.get("warnings", []),
            synthesis=GroundedSynthesis.model_validate(result["synthesis"]),
            critic=CriticReview.model_validate(result["critic"]),
            revision_count=result.get("revision_count", 0),
            grounded=result.get("grounded", False),
            second_retrieval_plan=(
                SecondRetrievalPlan.model_validate(result["second_retrieval_plan"])
                if result.get("second_retrieval_plan")
                else None
            ),
            retrieval_diagnostics=[
                RetrievalPassDiagnostic.model_validate(item)
                for item in result.get("retrieval_diagnostics", [])
            ],
        )

    def _run_retrieval(self, state: dict) -> dict:
        from app.core.config import get_settings
        from app.core.rag.research_planner import is_deep_research_question

        settings = get_settings()
        question = str(state.get("question") or "")
        if (
            self._orchestrator is not None
            and settings.research_deep_retrieval_enabled
            and is_deep_research_question(question)
        ):
            return self._run_deep_retrieval(state)

        if self._orchestrator is not None:
            record = self._document_pipeline_service.get_document(state["doc_id"])
            result = self._orchestrator.retrieve(
                state["question"],
                doc_id=state["doc_id"],
                company_id=state.get("company_id"),
                top_k=state["top_k"],
                company_name=record.metadata.company,
                company_aliases=list(record.metadata.company_aliases or []),
            )
            analysis = result.analysis.model_dump(mode="json")
            hits = self._serialize_hits(result.vector_hits)
            metrics = [item.model_dump(mode="json") for item in result.metrics]
            warnings = list(result.warnings)
            warnings, metrics = self._apply_doc_year_guard(
                record,
                analysis,
                warnings,
                metrics,
            )
            warnings.extend(self._entity_scope_conflict_warnings(metrics, analysis))
            second_retrieve_done = False
            retrieval_passes = 1
            second_plan: SecondRetrievalPlan | None = None
            retrieval_diagnostics = [
                self._retrieval_diagnostic(
                    pass_index=1,
                    query=state["question"],
                    result=result,
                )
            ]
            reason = self._second_retrieve_reason(
                hits=hits,
                metrics=metrics,
                graph_paths=result.graph_paths,
                warnings=warnings,
                analysis=analysis,
                question=str(state.get("question") or ""),
            )
            if reason and settings.research_agentic_second_pass_enabled:
                second_plan = self._build_second_retrieval_plan(
                    reason=reason,
                    question=state["question"],
                    analysis=analysis,
                    first_hit_count=len(hits),
                )
                second_result = self._orchestrator.retrieve(
                    second_plan.rewritten_query,
                    doc_id=state["doc_id"],
                    company_id=state.get("company_id"),
                    top_k=state["top_k"],
                    company_name=record.metadata.company,
                    company_aliases=list(record.metadata.company_aliases or []),
                    analysis_override=QueryAnalysis(
                        intent=analysis["intent"],
                        routes=second_plan.routes,
                        metric_keys=second_plan.metric_keys,
                        years=second_plan.years,
                        needs_growth=second_plan.needs_growth,
                        section_hints=second_plan.section_hints,
                        entity_scope=second_plan.entity_scope,
                    ),
                )
                second_metrics = [
                    item.model_dump(mode="json") for item in second_result.metrics
                ]
                second_warnings, second_metrics = self._apply_doc_year_guard(
                    record,
                    second_plan.model_dump(mode="json"),
                    list(second_result.warnings),
                    second_metrics,
                )
                second_diagnostic = self._retrieval_diagnostic(
                    pass_index=2,
                    query=second_plan.rewritten_query,
                    result=second_result,
                    reason=reason,
                    previous_hits=self._serialize_hits(result.vector_hits),
                    previous_metrics=[
                        item.model_dump(mode="json") for item in result.metrics
                    ],
                    previous_paths=[
                        item.model_dump(mode="json") for item in result.graph_paths
                    ],
                )
                prior_metric_ids = {
                    (
                        item.get("document_id"),
                        item.get("metric_key"),
                        item.get("period_year"),
                        item.get("value"),
                    )
                    for item in metrics
                }
                second_diagnostic["metric_count"] = len(second_metrics)
                second_diagnostic["new_metrics"] = sum(
                    tuple(
                        item.get(field)
                        for field in ("document_id", "metric_key", "period_year", "value")
                    )
                    not in prior_metric_ids
                    for item in second_metrics
                )
                extra = self._serialize_hits(second_result.vector_hits)
                if not any(
                    second_diagnostic[key]
                    for key in ("new_vector_hits", "new_metrics", "new_graph_paths")
                ):
                    fallback_hits = self._retriever.retrieve(
                        second_plan.rewritten_query,
                        doc_id=state["doc_id"],
                        top_k=state["top_k"],
                        section_hints=second_plan.section_hints,
                        metric_keys=second_plan.metric_keys,
                        years=second_plan.years or None,
                    )
                    extra = self._serialize_hits(fallback_hits)
                    previous_ids = {
                        item.get("segment_id")
                        for item in self._serialize_hits(result.vector_hits)
                    }
                    second_diagnostic["vector_hit_count"] += len(fallback_hits)
                    second_diagnostic["new_vector_hits"] = sum(
                        segment.segment_id not in previous_ids
                        for segment, _ in fallback_hits
                    )
                    warnings.append(
                        "Second retrieve orchestrator produced no new evidence; "
                        "used direct vector fallback"
                    )
                # A retry only runs after the first pass has an evidence gap.
                # Put the targeted results first so a full first-pass top_k does
                # not discard every newly retrieved segment during truncation.
                hits = self._merge_hits(extra, hits, state["top_k"])
                metrics = self._merge_records(
                    second_metrics,
                    metrics,
                    identity_fields=("document_id", "metric_key", "period_year", "value"),
                )
                graph_paths = self._merge_records(
                    [item.model_dump(mode="json") for item in second_result.graph_paths],
                    [item.model_dump(mode="json") for item in result.graph_paths],
                    identity_fields=("path_id",),
                    limit=state["top_k"],
                )
                calculations = self._merge_records(
                    [item.model_dump(mode="json") for item in second_result.calculations],
                    [item.model_dump(mode="json") for item in result.calculations],
                    identity_fields=("metric_key",),
                )
                warnings.append(f"Second retrieve: {reason}")
                warnings.extend(second_warnings)
                second_retrieve_done = True
                retrieval_passes = 2
                retrieval_diagnostics.append(second_diagnostic)
                fusion_summary = self._updated_fusion_summary(
                    result.fusion_summary,
                    routes=second_plan.routes,
                    hits=hits,
                    metrics=metrics,
                    graph_paths=graph_paths,
                )
            else:
                graph_paths = [
                    item.model_dump(mode="json") for item in result.graph_paths
                ]
                calculations = [
                    item.model_dump(mode="json") for item in result.calculations
                ]
                fusion_summary = (
                    result.fusion_summary.model_dump(mode="json")
                    if result.fusion_summary is not None
                    else None
                )
            return {
                "hits": hits,
                "query_analysis": analysis,
                "metrics": metrics,
                "calculations": calculations,
                "graph_paths": graph_paths,
                "fusion_summary": fusion_summary,
                "warnings": warnings,
                "second_retrieve_done": second_retrieve_done,
                "retrieval_passes": retrieval_passes,
                "second_retrieval_plan": (
                    second_plan.model_dump(mode="json") if second_plan else None
                ),
                "retrieval_diagnostics": retrieval_diagnostics,
            }

        hits = self._retriever.retrieve(
            state["question"],
            doc_id=state["doc_id"],
            top_k=state["top_k"],
        )
        return {
            "hits": self._serialize_hits(hits),
            "query_analysis": QueryAnalysis(
                intent="semantic",
                routes=["vector"],
            ).model_dump(mode="json"),
            "metrics": [],
            "calculations": [],
            "graph_paths": [],
            "fusion_summary": None,
            "warnings": [],
            "second_retrieve_done": False,
            "retrieval_passes": 1,
            "second_retrieval_plan": None,
            "retrieval_diagnostics": [
                {
                    "pass_index": 1,
                    "query": state["question"],
                    "routes": ["vector"],
                    "vector_hit_count": len(hits),
                    "metric_count": 0,
                    "graph_path_count": 0,
                    "new_vector_hits": len(hits),
                    "new_metrics": 0,
                    "new_graph_paths": 0,
                }
            ],
        }

    def _run_deep_retrieval(self, state: dict) -> dict:
        from app.core.rag.orchestrator import QueryAnalyzer
        from app.core.rag.research_planner import plan_deep_research

        assert self._orchestrator is not None
        record = self._document_pipeline_service.get_document(state["doc_id"])
        question = str(state["question"] or "")
        top_k = int(state["top_k"])
        analyzer = QueryAnalyzer()
        base_analysis = analyzer.analyze(question)

        hits: list[dict] = []
        metrics: list[dict] = []
        graph_paths: list[dict] = []
        calculations: list[dict] = []
        subtasks = plan_deep_research(question)
        warnings: list[str] = [f"Deep retrieval: {len(subtasks)} subtasks."]
        diagnostics: list[dict] = []
        subtask_ids: list[str] = []

        for pass_index, task in enumerate(subtasks, start=1):
            subtask_ids.append(task.task_id)
            override = QueryAnalysis(
                intent=base_analysis.intent,
                routes=list(base_analysis.routes),
                metric_keys=task.metric_keys or list(base_analysis.metric_keys),
                years=list(base_analysis.years),
                needs_growth=base_analysis.needs_growth,
                section_hints=task.section_hints or list(base_analysis.section_hints),
                entity_scope=base_analysis.entity_scope,
            )
            result = self._orchestrator.retrieve(
                task.question,
                doc_id=state["doc_id"],
                company_id=state.get("company_id"),
                top_k=top_k,
                company_name=record.metadata.company,
                company_aliases=list(record.metadata.company_aliases or []),
                analysis_override=override,
            )
            task_hits = self._serialize_hits(result.vector_hits)
            hits = self._merge_hits(hits, task_hits, top_k * 3)
            task_metrics = [item.model_dump(mode="json") for item in result.metrics]
            metrics = self._merge_records(
                task_metrics,
                metrics,
                identity_fields=("document_id", "metric_key", "period_year", "value"),
                limit=30,
            )
            task_paths = [item.model_dump(mode="json") for item in result.graph_paths]
            graph_paths = self._merge_records(
                task_paths,
                graph_paths,
                identity_fields=("path_id",),
                limit=top_k * 2,
            )
            task_calcs = [item.model_dump(mode="json") for item in result.calculations]
            calculations = self._merge_records(
                task_calcs,
                calculations,
                identity_fields=("metric_key",),
            )
            warnings.extend(result.warnings)
            diagnostics.append(
                self._retrieval_diagnostic(
                    pass_index=pass_index,
                    query=task.question,
                    result=result,
                    reason=f"deep_subtask:{task.task_id}",
                )
            )

        analysis = base_analysis.model_dump(mode="json")
        warnings, metrics = self._apply_doc_year_guard(
            record,
            analysis,
            warnings,
            metrics,
        )
        warnings.extend(self._entity_scope_conflict_warnings(metrics, analysis))
        fusion_summary = FusionSummary(
            query_intent=analysis.get("intent") or "hybrid",
            routes=list(dict.fromkeys(analysis.get("routes") or [])),
            vector_snippet_count=len(hits),
            metric_count=len(metrics),
            graph_path_count=len(graph_paths),
            summary=(
                f"Deep research fused {len(hits)} snippets, "
                f"{len(metrics)} metrics, {len(graph_paths)} graph paths "
                f"across {len(subtask_ids)} subtasks."
            ),
        ).model_dump(mode="json")

        return {
            "hits": hits,
            "query_analysis": analysis,
            "metrics": metrics,
            "calculations": calculations,
            "graph_paths": graph_paths,
            "fusion_summary": fusion_summary,
            "warnings": warnings,
            "second_retrieve_done": False,
            "retrieval_passes": len(subtask_ids),
            "second_retrieval_plan": None,
            "research_subtasks": subtask_ids,
            "retrieval_diagnostics": diagnostics,
        }

    def _synthesize_answer(self, state: dict) -> dict:
        # Retrieval keeps clean ``question``; synthesis may include chat-memory context.
        synthesis_question = str(
            state.get("synthesis_question") or state.get("question") or ""
        )
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
                question=synthesis_question,
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
                evidence=evidence,
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
                metrics=list(state.get("metrics") or []),
                query_analysis=state.get("query_analysis"),
            )
            return {
                "critic": review.model_dump(mode="json"),
                "grounded": review.passed,
            }
        except Exception as exc:
            message = str(exc)
            is_timeout = "timeout" in message.lower() or "timed out" in message.lower()
            # Soft-fail timeouts: keep draft, skip revise burn, never mark grounded.
            review = CriticReview(
                passed=False,
                score=0.0,
                issues=[
                    CriticIssue(
                        category="logic_error",
                        severity="medium" if is_timeout else "high",
                        message=(
                            f"Critic timed out: {type(exc).__name__}"
                            if is_timeout
                            else f"Critic execution failed: {type(exc).__name__}"
                        ),
                    )
                ],
                summary=(
                    "Critic timed out; answer kept but not marked grounded."
                    if is_timeout
                    else "Critic failed; answer cannot be marked grounded."
                ),
            )
            # Still apply deterministic citation checks when possible.
            try:
                review = self._grounded_engine._apply_deterministic_checks(
                    review,
                    synthesis,
                    state.get("evidence", []),
                    question=state["question"],
                    metrics=list(state.get("metrics") or []),
                    query_analysis=state.get("query_analysis") or {},
                )
            except Exception:  # noqa: BLE001
                pass
            return {
                "critic": review.model_dump(mode="json"),
                "grounded": False,
                "warnings": [
                    *state.get("warnings", []),
                    (
                        f"critic timed out: {exc}"
                        if is_timeout
                        else f"critic failed: {exc}"
                    ),
                ],
                # Soft-fail: keep draft, skip revision burn (critic already unavailable).
                "revision_count": state.get("max_revisions", 0),
            }

    def _revise_answer(self, state: dict) -> dict:
        if self._grounded_engine is None:
            return {"revision_count": state.get("max_revisions", 0)}

        updates: dict = {}
        working = dict(state)
        if self._should_critic_reretrieve(state):
            analysis = state.get("query_analysis") or {}
            analysis = analysis if isinstance(analysis, dict) else {}
            plan = self._build_second_retrieval_plan(
                reason="complementary section",
                question=state["question"],
                analysis=analysis,
                first_hit_count=len(state.get("hits") or []),
            )
            diagnostic: dict | None = None
            extra_hits = []
            second_warnings: list[str] = []
            if self._orchestrator is not None:
                record = self._document_pipeline_service.get_document(state["doc_id"])
                second_result = self._orchestrator.retrieve(
                    plan.rewritten_query,
                    doc_id=state["doc_id"],
                    company_id=state.get("company_id"),
                    top_k=state.get("top_k") or 3,
                    company_name=record.metadata.company,
                    company_aliases=list(record.metadata.company_aliases or []),
                    analysis_override=QueryAnalysis(
                        intent=analysis.get("intent", "semantic"),
                        routes=plan.routes,
                        metric_keys=plan.metric_keys,
                        years=plan.years,
                        needs_growth=plan.needs_growth,
                        section_hints=plan.section_hints,
                        entity_scope=plan.entity_scope,
                    ),
                )
                extra_hits = second_result.vector_hits
                diagnostic = self._retrieval_diagnostic(
                    pass_index=2,
                    query=plan.rewritten_query,
                    result=second_result,
                    reason="critic missing_evidence",
                    previous_hits=list(state.get("hits") or []),
                    previous_metrics=list(state.get("metrics") or []),
                    previous_paths=list(state.get("graph_paths") or []),
                )
                second_metrics = [
                    item.model_dump(mode="json") for item in second_result.metrics
                ]
                second_warnings, second_metrics = self._apply_doc_year_guard(
                    record,
                    plan.model_dump(mode="json"),
                    list(second_result.warnings),
                    second_metrics,
                )
                prior_metric_ids = {
                    (
                        item.get("document_id"),
                        item.get("metric_key"),
                        item.get("period_year"),
                        item.get("value"),
                    )
                    for item in state.get("metrics") or []
                }
                diagnostic["metric_count"] = len(second_metrics)
                diagnostic["new_metrics"] = sum(
                    tuple(
                        item.get(field)
                        for field in ("document_id", "metric_key", "period_year", "value")
                    )
                    not in prior_metric_ids
                    for item in second_metrics
                )
                working["metrics"] = self._merge_records(
                    second_metrics,
                    list(state.get("metrics") or []),
                    identity_fields=("document_id", "metric_key", "period_year", "value"),
                )
                working["graph_paths"] = self._merge_records(
                    [item.model_dump(mode="json") for item in second_result.graph_paths],
                    list(state.get("graph_paths") or []),
                    identity_fields=("path_id",),
                    limit=int(state.get("top_k") or 3),
                )
            if not extra_hits:
                extra_hits = self._retriever.retrieve(
                    plan.rewritten_query,
                    doc_id=state["doc_id"],
                    top_k=state.get("top_k") or 3,
                    section_hints=plan.section_hints,
                    metric_keys=plan.metric_keys,
                    years=plan.years or None,
                )
            hits = self._merge_hits(
                self._serialize_hits(extra_hits),
                list(state.get("hits") or []),
                int(state.get("top_k") or 3),
            )
            warnings = [
                *list(state.get("warnings") or []),
                "Second retrieve: critic missing_evidence",
                *second_warnings,
            ]
            working["hits"] = hits
            working["warnings"] = warnings
            working["second_retrieve_done"] = True
            working["retrieval_passes"] = 2
            working["second_retrieval_plan"] = plan.model_dump(mode="json")
            diagnostics = list(state.get("retrieval_diagnostics") or [])
            if diagnostic is not None:
                diagnostics.append(diagnostic)
            working["retrieval_diagnostics"] = diagnostics
            if self._orchestrator is not None:
                first_summary = (
                    FusionSummary.model_validate(state["fusion_summary"])
                    if state.get("fusion_summary")
                    else None
                )
                working["fusion_summary"] = self._updated_fusion_summary(
                    first_summary,
                    routes=plan.routes,
                    hits=hits,
                    metrics=working.get("metrics", []),
                    graph_paths=working.get("graph_paths", []),
                )
            working["evidence"] = self._grounded_engine.build_evidence(working)
            updates.update(
                {
                    "hits": hits,
                    "warnings": warnings,
                    "second_retrieve_done": True,
                    "retrieval_passes": 2,
                    "second_retrieval_plan": working["second_retrieval_plan"],
                    "retrieval_diagnostics": diagnostics,
                    "metrics": working.get("metrics", state.get("metrics", [])),
                    "graph_paths": working.get(
                        "graph_paths", state.get("graph_paths", [])
                    ),
                    "fusion_summary": working.get(
                        "fusion_summary", state.get("fusion_summary")
                    ),
                    "evidence": working["evidence"],
                }
            )

        try:
            synthesis = self._grounded_engine.synthesize(
                question=state["question"],
                evidence=working.get("evidence", []),
                previous_draft=GroundedSynthesis.model_validate(state["synthesis"]),
                critic_review=CriticReview.model_validate(state["critic"]),
            )
            return {
                **updates,
                "synthesis": synthesis.model_dump(mode="json"),
                "answer": synthesis.answer,
                "revision_count": state.get("revision_count", 0) + 1,
            }
        except Exception as exc:
            return {
                **updates,
                "warnings": [
                    *list(working.get("warnings") or state.get("warnings") or []),
                    f"revision failed: {exc}",
                ],
                "revision_count": state.get("max_revisions", 0),
            }

    @staticmethod
    def _serialize_hits(pairs) -> list[dict]:
        return [
            {
                "segment_id": segment.segment_id,
                "score": round(score, 4),
                "content": segment.content,
                "metadata": dict(segment.metadata or {}),
            }
            for segment, score in pairs
        ]

    @staticmethod
    def _merge_hits(first: list[dict], second: list[dict], top_k: int) -> list[dict]:
        merged = list(first)
        seen = {hit.get("segment_id") for hit in merged}
        for hit in second:
            segment_id = hit.get("segment_id")
            if segment_id in seen:
                continue
            seen.add(segment_id)
            merged.append(hit)
            if len(merged) >= top_k:
                break
        return merged[:top_k]

    @staticmethod
    def _merge_records(
        first: list[dict],
        second: list[dict],
        *,
        identity_fields: tuple[str, ...],
        limit: int | None = None,
    ) -> list[dict]:
        merged: list[dict] = []
        seen: set[tuple[object, ...]] = set()
        for item in (*first, *second):
            identity = tuple(item.get(field) for field in identity_fields)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(item)
            if limit is not None and len(merged) >= limit:
                break
        return merged

    @staticmethod
    def _updated_fusion_summary(
        first: FusionSummary | None,
        *,
        routes: list[str],
        hits: list[dict],
        metrics: list[dict],
        graph_paths: list[dict],
    ) -> dict:
        summary = first or FusionSummary(query_intent="agentic_retry")
        merged_routes = list(dict.fromkeys([*summary.routes, *routes]))
        updated = summary.model_copy(
            update={
                "routes": merged_routes,
                "vector_snippet_count": len(hits),
                "metric_count": len(metrics),
                "graph_path_count": len(graph_paths),
                "summary": (
                    "Agentic retrieval fused "
                    f"{len(hits)} text snippets, {len(metrics)} metrics, "
                    f"and {len(graph_paths)} graph paths."
                ),
            }
        )
        return updated.model_dump(mode="json")

    @staticmethod
    def _retrieval_diagnostic(
        *,
        pass_index: int,
        query: str,
        result: OrchestratedRetrievalResult,
        reason: str | None = None,
        previous_hits: list[dict] | None = None,
        previous_metrics: list[dict] | None = None,
        previous_paths: list[dict] | None = None,
    ) -> dict:
        hit_ids = {item.get("segment_id") for item in previous_hits or []}
        metric_ids = {
            (
                item.get("document_id"),
                item.get("metric_key"),
                item.get("period_year"),
                item.get("value"),
            )
            for item in previous_metrics or []
        }
        path_ids = {item.get("path_id") for item in previous_paths or []}
        return RetrievalPassDiagnostic(
            pass_index=pass_index,
            reason=reason,
            query=query,
            routes=list(result.analysis.routes),
            vector_hit_count=len(result.vector_hits),
            metric_count=len(result.metrics),
            graph_path_count=len(result.graph_paths),
            new_vector_hits=sum(
                segment.segment_id not in hit_ids for segment, _ in result.vector_hits
            ),
            new_metrics=sum(
                (
                    item.document_id,
                    item.metric_key,
                    item.period_year,
                    item.value,
                )
                not in metric_ids
                for item in result.metrics
            ),
            new_graph_paths=sum(item.path_id not in path_ids for item in result.graph_paths),
        ).model_dump(mode="json")

    def _build_second_retrieval_plan(
        self,
        *,
        reason: str,
        question: str,
        analysis: dict,
        first_hit_count: int,
    ) -> SecondRetrievalPlan:
        kwargs = self._second_pass_kwargs(
            reason,
            analysis,
            first_hit_count=first_hit_count,
        )
        routes = list(analysis.get("routes") or [])
        if "vector" not in routes:
            routes.append("vector")
        if reason == "insufficient metrics" and "sql" not in routes:
            routes.append("sql")
        suffixes = {
            "explanation section": "管理层讨论与分析 原因 驱动因素",
            "complementary section": "补充章节 相关披露",
            "insufficient metrics": "财务报表 指标 数值",
            "insufficient year": "对应报告期 财务数据",
            "empty evidence": "相关财务披露",
        }
        suffix = suffixes.get(reason, "补充证据")
        return SecondRetrievalPlan(
            reason=reason,
            rewritten_query=f"{question} {suffix}".strip(),
            routes=routes,
            metric_keys=list(kwargs.get("metric_keys") or []),
            years=list(kwargs.get("years") or []),
            needs_growth=bool(analysis.get("needs_growth")),
            section_hints=list(kwargs.get("section_hints") or []),
            entity_scope=analysis.get("entity_scope", "unknown"),
            budget=1,
        )

    @staticmethod
    def _entity_scope_conflict_warnings(
        metrics: list[dict],
        analysis: dict,
    ) -> list[str]:
        """Flag when multiple entity scopes compete for the same metric period."""
        if not metrics:
            return []
        requested_scope = analysis.get("entity_scope")
        grouped: dict[tuple[str, str], set[str]] = {}
        for item in metrics:
            key = (str(item.get("metric_key") or ""), str(item.get("period") or ""))
            scope = str(item.get("entity_scope") or "unknown")
            grouped.setdefault(key, set()).add(scope)
        conflicts = [
            key
            for key, scopes in grouped.items()
            if len(scopes) > 1 and "unknown" not in scopes
        ]
        if not conflicts:
            return []
        if requested_scope in {"consolidated", "parent_company"}:
            return [
                (
                    "Entity scope conflict: multiple scopes present for "
                    f"{conflicts[0][0]} {conflicts[0][1]}; prefer {requested_scope}."
                )
            ]
        return [
            (
                "Entity scope conflict: multiple scopes present for "
                f"{conflicts[0][0]} {conflicts[0][1]}."
            )
        ]

    @staticmethod
    def _apply_doc_year_guard(
        record,
        analysis: dict,
        warnings: list[str],
        metrics: list[dict],
    ) -> tuple[list[str], list[dict]]:
        doc_year = getattr(getattr(record, "metadata", None), "year", None)
        years = [int(year) for year in (analysis.get("years") or [])]
        needs_growth = bool(analysis.get("needs_growth"))
        if isinstance(doc_year, int) and years:
            year_ok = doc_year in years
            if not year_ok and needs_growth:
                year_ok = all(doc_year in {year, year - 1} for year in years)
            if not year_ok:
                warnings = [
                    *warnings,
                    (
                        f"Pinned document year {doc_year} does not match "
                        f"question years {years}; do not treat other-year "
                        "figures as the asked period."
                    ),
                ]
        if not years:
            return warnings, metrics
        allowed = set(years)
        if needs_growth:
            allowed.update(year - 1 for year in years)
        kept = []
        for item in metrics:
            period_year = item.get("period_year")
            if period_year is None or period_year in allowed:
                kept.append(item)
        return warnings, kept

    _EXPLANATION_CUES = ("为什么", "为何", "why", "reason", "原因", "explain")

    @staticmethod
    def _hit_section_types(hits: list) -> set[str]:
        types: set[str] = set()
        for hit in hits:
            metadata = hit.get("metadata") if isinstance(hit, dict) else None
            section_type = (metadata or {}).get("section_type")
            if section_type:
                types.add(str(section_type))
        return types

    @staticmethod
    def _is_explanation_query(question: str, analysis: dict) -> bool:
        text = question.casefold()
        if any(cue in text for cue in ResearchService._EXPLANATION_CUES):
            return True
        return bool(
            analysis.get("needs_growth")
            and "vector" in list(analysis.get("routes") or [])
        )

    @staticmethod
    def _second_retrieve_reason(
        *,
        hits: list,
        metrics: list,
        graph_paths: list,
        warnings: list[str],
        analysis: dict,
        question: str = "",
    ) -> str | None:
        vector_active = "vector" in list(analysis.get("routes") or [])
        no_vector = vector_active and not hits
        no_metrics = not metrics
        no_graph = not graph_paths
        sql_active = "sql" in list(analysis.get("routes") or [])
        thin = no_vector or (sql_active and no_metrics)
        joined = " ".join(warnings)
        year_relaxed = "year constraint relaxed" in joined
        section_relaxed = "section constraint relaxed" in joined
        hints = list(analysis.get("section_hints") or [])
        if not hits and no_metrics and no_graph:
            if hints:
                return "complementary section"
            return "empty evidence"
        if no_vector and hints:
            return "complementary section"
        if (year_relaxed or section_relaxed) and thin:
            if section_relaxed and hints:
                return "complementary section"
            if year_relaxed:
                return "year constraint relaxed"
            return "section constraint relaxed"
        gap = ResearchService._evidence_gap(
            hits=hits,
            metrics=metrics,
            analysis=analysis,
        )
        if gap:
            return gap
        if (
            hits
            and ResearchService._is_explanation_query(question, analysis)
            and "management_discussion" not in ResearchService._hit_section_types(hits)
        ):
            return "explanation section"
        return None

    @staticmethod
    def _evidence_gap(
        *,
        hits: list,
        metrics: list,
        analysis: dict,
    ) -> str | None:
        """FinanceBench-style entity match: asked metric/year must appear in evidence."""
        metric_keys = [str(key) for key in (analysis.get("metric_keys") or []) if key]
        years = [int(year) for year in (analysis.get("years") or [])]
        haystack = " ".join(str(hit.get("content") or "") for hit in hits).casefold()
        if metric_keys:
            present = {str(item.get("metric_key") or "") for item in metrics}
            mentioned = any(
                key.casefold() in haystack or key.replace("_", " ") in haystack
                for key in metric_keys
            )
            if not (present & set(metric_keys)) and not mentioned:
                return "insufficient metrics"
        if years:
            metric_years = {
                int(item["period_year"])
                for item in metrics
                if item.get("period_year") is not None
            }
            mentioned_year = any(str(year) in haystack for year in years)
            if metric_years.isdisjoint(set(years)) and not mentioned_year:
                return "insufficient year"
        return None

    @staticmethod
    def _complementary_section_hints(
        hints: list[str],
        *,
        first_hit_count: int,
    ) -> list[str]:
        has_risk = "risk_section" in hints
        has_mda = "management_discussion" in hints
        if has_risk and not has_mda:
            return ["management_discussion"]
        if has_mda and not has_risk:
            if first_hit_count == 0:
                return []
            return ["risk_section"]
        return []

    def _second_pass_kwargs(
        self,
        reason: str,
        analysis: dict,
        *,
        first_hit_count: int,
    ) -> dict:
        metric_keys = list(analysis.get("metric_keys") or [])
        section_hints = list(analysis.get("section_hints") or [])
        years = list(analysis.get("years") or [])
        if reason == "explanation section":
            return {
                "section_hints": ["management_discussion"],
                "metric_keys": metric_keys,
                "years": years or None,
            }
        if reason == "complementary section":
            return {
                "section_hints": self._complementary_section_hints(
                    section_hints,
                    first_hit_count=first_hit_count,
                ),
                "metric_keys": metric_keys,
                "years": years or None,
            }
        if reason == "insufficient metrics":
            return {
                "section_hints": [],
                "metric_keys": metric_keys,
                "years": years or None,
            }
        if reason == "empty evidence":
            return {
                "section_hints": section_hints,
                "metric_keys": metric_keys,
                "years": years or None,
            }
        return {
            "section_hints": section_hints,
            "metric_keys": metric_keys,
            "years": None,
        }

    @staticmethod
    def _should_critic_reretrieve(state: dict) -> bool:
        if state.get("second_retrieve_done"):
            return False
        if int(state.get("retrieval_passes") or 1) >= 2:
            return False
        issues = (state.get("critic") or {}).get("issues") or []
        for issue in issues:
            category = (
                issue.get("category")
                if isinstance(issue, dict)
                else getattr(issue, "category", None)
            )
            if category == "missing_evidence":
                return True
        return False

    def _fallback_synthesis(
        self,
        state: dict,
        *,
        limitation: str = "Formal LLM grounded synthesis is not configured.",
        evidence: list[dict] | None = None,
    ) -> GroundedSynthesis:
        evidence_items = list(evidence or [])
        if not evidence_items and self._grounded_engine is not None:
            evidence_items = self._grounded_engine.build_evidence(state)

        graph_paths = state.get("graph_paths") or []
        query_analysis = state.get("query_analysis") or {}
        graph_rel_types = self._graph_relationship_types(graph_paths, evidence_items)
        fallback_mode = self._select_fallback_mode(
            state,
            graph_rel_types=graph_rel_types,
            query_analysis=query_analysis,
        )

        citations: list[GroundedCitation] = []
        key_findings: list[str] = []
        answer_parts: list[str] = []
        synthesis_note = "（注：LLM 综合生成暂不可用，以下为基于检索证据的简要草稿。）"

        if fallback_mode == "industry":
            industries = self._extract_industry_names(graph_paths, evidence_items)
            if industries:
                answer_parts.append(
                    f"公司经营所在行业为：{'、'.join(industries)}。"
                )
                key_findings.append(f"行业：{'、'.join(industries)}")
                for evidence_id in self._graph_evidence_ids(
                    evidence_items, "OPERATES_IN"
                )[:1]:
                    citations.append(
                        GroundedCitation(
                            evidence_id=evidence_id,
                            claim=f"公司所在行业为 {industries[0]}",
                        )
                    )

        elif fallback_mode == "metric_graph":
            metric_keys = self._extract_graph_metric_keys(graph_paths, evidence_items)
            if metric_keys:
                display = "、".join(metric_keys[:12])
                if len(metric_keys) > 12:
                    display = f"{display} 等共 {len(metric_keys)} 项"
                answer_parts.append(f"公司报告并关联的财务指标包括：{display}。")
                key_findings.append(f"关联指标：{display}")
                for evidence_id in self._graph_evidence_ids(
                    evidence_items, "REPORTS_METRIC"
                )[:3]:
                    citations.append(
                        GroundedCitation(
                            evidence_id=evidence_id,
                            claim="公司 REPORTS_METRIC 关系关联财务指标",
                        )
                    )

        elif fallback_mode == "vector":
            vector_items = [
                item for item in evidence_items if item.get("source_type") == "vector"
            ]
            if not vector_items and state.get("hits"):
                vector_items = [
                    {
                        "evidence_id": f"V{index}",
                        "source_type": "vector",
                        "content": hit["content"],
                    }
                    for index, hit in enumerate(state["hits"][:2], start=1)
                ]
            snippets: list[str] = []
            for item in vector_items[:2]:
                snippet = self._clean_vector_snippet(item.get("content", ""))
                if not snippet:
                    continue
                evidence_id = str(item.get("evidence_id") or "")
                marker = f"[{evidence_id}]" if evidence_id else ""
                snippets.append(f"{marker}{snippet}")
                if evidence_id:
                    citations.append(
                        GroundedCitation(
                            evidence_id=evidence_id,
                            claim=snippet[:120],
                        )
                    )
            if snippets:
                answer_parts.append("根据检索到的相关段落：")
                answer_parts.extend(snippets)
                key_findings.extend(snippets[:2])

        elif fallback_mode == "structured" and state.get("metrics"):
            metric_lines = [
                (
                    f"{item['metric_key']}({item['period']})="
                    f"{item['value']} {item.get('unit') or ''} "
                    f"{item.get('currency') or ''}"
                ).strip()
                for item in state["metrics"][:10]
            ]
            answer_parts.append(
                "检索到的结构化指标如下：" + "；".join(metric_lines) + "。"
            )
            key_findings.extend(metric_lines[:3])
            for index, item in enumerate(state["metrics"][:3], start=1):
                citations.append(
                    GroundedCitation(
                        evidence_id=f"S{index}",
                        claim=(
                            f"{item['metric_key']}({item['period']})={item['value']}"
                        ),
                    )
                )

        if not answer_parts:
            answer = "当前没有检索到足够的文本或结构化证据，无法生成可靠回答。"
        else:
            answer = "\n\n".join(answer_parts) + f"\n\n{synthesis_note}"

        return GroundedSynthesis(
            answer=answer,
            key_findings=key_findings,
            citations=citations,
            confidence=0.25,
            limitations=[limitation],
        )

    @staticmethod
    def _graph_relationship_types(
        graph_paths: list[dict],
        evidence_items: list[dict],
    ) -> set[str]:
        rel_types: set[str] = set()
        for path in graph_paths:
            for relationship in path.get("relationships") or []:
                rel_type = relationship.get("relationship_type")
                if rel_type:
                    rel_types.add(str(rel_type))
        for item in evidence_items:
            if item.get("source_type") != "graph":
                continue
            for relationship in item.get("relationships") or []:
                rel_type = relationship.get("relationship_type")
                if rel_type:
                    rel_types.add(str(rel_type))
        return rel_types

    @staticmethod
    def _select_fallback_mode(
        state: dict,
        *,
        graph_rel_types: set[str],
        query_analysis: dict,
    ) -> str:
        question = state.get("question", "")
        intent = query_analysis.get("intent", "semantic")
        routes = list(query_analysis.get("routes") or [])

        if "行业" in question and "OPERATES_IN" in graph_rel_types:
            return "industry"
        if (
            any(term in question for term in ("指标", "关联", "报告"))
            and "REPORTS_METRIC" in graph_rel_types
        ):
            return "metric_graph"
        if "OPERATES_IN" in graph_rel_types and "REPORTS_METRIC" not in graph_rel_types:
            return "industry"
        if "REPORTS_METRIC" in graph_rel_types and "OPERATES_IN" not in graph_rel_types:
            return "metric_graph"
        if intent == "structured" or ("sql" in routes and "vector" not in routes):
            return "structured"
        if intent == "semantic" or "vector" in routes:
            return "vector"
        if state.get("metrics"):
            return "structured"
        if state.get("hits"):
            return "vector"
        return "vector"

    @staticmethod
    def _extract_industry_names(
        graph_paths: list[dict],
        evidence_items: list[dict],
    ) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()

        def add_name(name: str | None) -> None:
            cleaned = (name or "").strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                names.append(cleaned)

        for path in graph_paths:
            node_map = {
                node.get("node_id"): node for node in path.get("nodes") or []
            }
            for relationship in path.get("relationships") or []:
                if relationship.get("relationship_type") != "OPERATES_IN":
                    continue
                target = node_map.get(relationship.get("target_node_id"))
                if target is not None:
                    add_name(target.get("name"))
            for node in path.get("nodes") or []:
                if node.get("node_type") == "industry":
                    add_name(node.get("name"))

        for item in evidence_items:
            if item.get("source_type") != "graph":
                continue
            node_map = {
                node.get("node_id"): node for node in item.get("nodes") or []
            }
            for relationship in item.get("relationships") or []:
                if relationship.get("relationship_type") != "OPERATES_IN":
                    continue
                target = node_map.get(relationship.get("target_node_id"))
                if target is not None:
                    add_name(target.get("name"))
            for node in item.get("nodes") or []:
                if node.get("node_type") == "industry":
                    add_name(node.get("name"))
        return names

    @staticmethod
    def _extract_graph_metric_keys(
        graph_paths: list[dict],
        evidence_items: list[dict],
    ) -> list[str]:
        keys: list[str] = []
        seen: set[str] = set()

        def add_key(raw_key: str | None) -> None:
            cleaned = (raw_key or "").strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                keys.append(cleaned)

        def collect_from_path(path: dict) -> None:
            node_map = {
                node.get("node_id"): node for node in path.get("nodes") or []
            }
            for relationship in path.get("relationships") or []:
                if relationship.get("relationship_type") != "REPORTS_METRIC":
                    continue
                target = node_map.get(relationship.get("target_node_id"))
                if target is None:
                    continue
                properties = target.get("properties") or {}
                add_key(target.get("name") or properties.get("metric_key"))
            for node in path.get("nodes") or []:
                if node.get("node_type") != "metric":
                    continue
                properties = node.get("properties") or {}
                add_key(node.get("name") or properties.get("metric_key"))

        for path in graph_paths:
            collect_from_path(path)
        for item in evidence_items:
            if item.get("source_type") == "graph":
                collect_from_path(item)
        return keys

    @staticmethod
    def _graph_evidence_ids(
        evidence_items: list[dict],
        relationship_type: str,
    ) -> list[str]:
        evidence_ids: list[str] = []
        for item in evidence_items:
            if item.get("source_type") != "graph":
                continue
            relationships = item.get("relationships") or []
            if any(
                rel.get("relationship_type") == relationship_type
                for rel in relationships
            ):
                evidence_id = item.get("evidence_id")
                if evidence_id:
                    evidence_ids.append(str(evidence_id))
        return evidence_ids

    @staticmethod
    def _clean_vector_snippet(content: str, *, max_len: int = 220) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line in seen:
                continue
            seen.add(line)
            lines.append(line)
        text = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if len(text) <= max_len:
            return text
        truncated = text[:max_len]
        for separator in ("。", "；", "，", ".", ";", ","):
            index = truncated.rfind(separator)
            if index > max_len // 2:
                return truncated[: index + 1].strip()
        return truncated.rstrip() + "…"
