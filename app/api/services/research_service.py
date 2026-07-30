import re

from app.core.db import build_company_id
from app.core.llm import GroundedResearchEngine
from app.core.rag import LocalRetriever, RetrievalOrchestrator
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
                        "metadata": dict(segment.metadata or {}),
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
                "fusion_summary": (
                    result.fusion_summary.model_dump(mode="json")
                    if result.fusion_summary is not None
                    else None
                ),
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
                    "metadata": dict(segment.metadata or {}),
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
            "fusion_summary": None,
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
