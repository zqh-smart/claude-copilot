from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.api.services.research_service import ResearchService
from app.core.rag import LocalRetriever
from app.core.rag.orchestrator import OrchestratedRetrievalResult
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService
from src.claude_copilot.schemas.document import DocumentSegment
from src.claude_copilot.schemas.financial_data import FinancialMetricObservation
from src.claude_copilot.schemas.knowledge_graph import GraphPath
from src.claude_copilot.schemas.research import CriticReview, GroundedSynthesis, QueryAnalysis


class _FailingGroundedEngine:
    def build_evidence(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for index, hit in enumerate(state.get("hits", []), start=1):
            evidence.append(
                {
                    "evidence_id": f"V{index}",
                    "source_type": "vector",
                    "source_id": hit["segment_id"],
                    "score": hit["score"],
                    "content": hit["content"],
                }
            )
        for index, item in enumerate(state.get("graph_paths", []), start=1):
            evidence.append(
                {
                    "evidence_id": f"G{index}",
                    "source_type": "graph",
                    "source_id": item["path_id"],
                    "summary": item["summary"],
                    "score": item["score"],
                    "nodes": item.get("nodes", []),
                    "relationships": item.get("relationships", []),
                }
            )
        return evidence

    def synthesize(self, **kwargs: Any) -> GroundedSynthesis:
        raise RuntimeError("LLM unavailable")

    def critique(self, **kwargs: Any) -> CriticReview:
        return CriticReview(
            passed=True,
            score=0.9,
            issues=[],
            summary="ok",
        )


def _make_service() -> ResearchService:
    return ResearchService(
        document_pipeline_service=DocumentPipelineService.__new__(DocumentPipelineService),
        retriever=LocalRetriever.__new__(LocalRetriever),
        grounded_engine=_FailingGroundedEngine(),  # type: ignore[arg-type]
    )


def test_fallback_industry_graph_on_synthesis_failure() -> None:
    service = _make_service()
    state = {
        "question": "公司经营所在的行业是什么？",
        "query_analysis": {"intent": "relational", "routes": ["graph"]},
        "graph_paths": [
            {
                "path_id": "rel:industry",
                "summary": "北京指南针 -[OPERATES_IN]-> 金融信息服务",
                "score": 0.91,
                "nodes": [
                    {
                        "node_id": "company:1",
                        "node_type": "company",
                        "name": "北京指南针",
                    },
                    {
                        "node_id": "industry:1",
                        "node_type": "industry",
                        "name": "金融信息服务",
                    },
                ],
                "relationships": [
                    {
                        "relationship_type": "OPERATES_IN",
                        "source_node_id": "company:1",
                        "target_node_id": "industry:1",
                    }
                ],
            }
        ],
        "hits": [],
        "metrics": [],
    }

    result = service._synthesize_answer(state)

    assert "公司经营所在行业为：金融信息服务。" in result["answer"]
    assert "OPERATES_IN" not in result["answer"]
    assert "LLM 综合生成暂不可用" in result["answer"]
    assert result["synthesis"]["citations"]
    assert result["synthesis"]["citations"][0]["evidence_id"] == "G1"
    assert any("grounded synthesis failed" in warning for warning in result["warnings"])


def test_fallback_reports_metric_graph_on_synthesis_failure() -> None:
    service = _make_service()
    state = {
        "question": "公司报告了哪些财务指标关联？",
        "query_analysis": {"intent": "relational", "routes": ["graph"]},
        "graph_paths": [
            {
                "path_id": "rel:metric-a",
                "summary": "ACME -[REPORTS_METRIC]-> revenue",
                "score": 0.88,
                "nodes": [
                    {"node_id": "company:1", "node_type": "company", "name": "ACME"},
                    {
                        "node_id": "metric:revenue",
                        "node_type": "metric",
                        "name": "revenue",
                        "properties": {"metric_key": "revenue"},
                    },
                ],
                "relationships": [
                    {
                        "relationship_type": "REPORTS_METRIC",
                        "source_node_id": "company:1",
                        "target_node_id": "metric:revenue",
                    }
                ],
            },
            {
                "path_id": "rel:metric-b",
                "summary": "ACME -[REPORTS_METRIC]-> net_income",
                "score": 0.85,
                "nodes": [
                    {"node_id": "company:1", "node_type": "company", "name": "ACME"},
                    {
                        "node_id": "metric:net_income",
                        "node_type": "metric",
                        "name": "net_income",
                        "properties": {"metric_key": "net_income"},
                    },
                ],
                "relationships": [
                    {
                        "relationship_type": "REPORTS_METRIC",
                        "source_node_id": "company:1",
                        "target_node_id": "metric:net_income",
                    }
                ],
            },
        ],
        "hits": [],
        "metrics": [],
    }

    result = service._synthesize_answer(state)

    assert "公司报告并关联的财务指标包括：revenue、net_income。" in result["answer"]
    assert "-[REPORTS_METRIC]->" not in result["answer"]
    assert len(result["synthesis"]["citations"]) >= 1


def test_critique_timeout_keeps_draft_and_skips_revision_burn() -> None:
    class _TimeoutEngine(_FailingGroundedEngine):
        def critique(self, **kwargs: Any) -> CriticReview:
            raise TimeoutError("LLM critic timed out after 30s")

        def _apply_deterministic_checks(self, review, synthesis, evidence):  # noqa: ANN001
            return review

    service = ResearchService(
        document_pipeline_service=DocumentPipelineService.__new__(DocumentPipelineService),
        retriever=LocalRetriever.__new__(LocalRetriever),
        grounded_engine=_TimeoutEngine(),  # type: ignore[arg-type]
    )
    state = {
        "question": "营收为何增长？",
        "synthesis": GroundedSynthesis(
            answer="draft kept",
            confidence=0.4,
            limitations=[],
            citations=[],
        ).model_dump(mode="json"),
        "evidence": [],
        "warnings": [],
        "revision_count": 0,
        "max_revisions": 1,
    }

    result = service._critique_answer(state)

    assert result["grounded"] is False
    assert result["revision_count"] == 1
    assert "Critic timed out" in result["critic"]["issues"][0]["message"]
    assert result["critic"]["issues"][0]["severity"] == "medium"
    assert any("critic timed out" in w for w in result["warnings"])


def test_fallback_mda_vector_on_synthesis_failure() -> None:
    service = _make_service()
    repeated_header = "管理层讨论与分析"
    state = {
        "question": "管理层如何讨论与分析公司经营情况？",
        "query_analysis": {"intent": "semantic", "routes": ["vector"]},
        "graph_paths": [],
        "metrics": [],
        "hits": [
            {
                "segment_id": "seg-1",
                "score": 0.92,
                "content": (
                    f"{repeated_header}\n"
                    f"{repeated_header}\n"
                    f"{repeated_header}\n"
                    "公司2021年营业收入稳步增长，主营业务保持扩张。"
                ),
            },
            {
                "segment_id": "seg-2",
                "score": 0.81,
                "content": "管理层认为行业竞争加剧，但公司仍通过产品升级维持市场份额。",
            },
        ],
    }

    result = service._synthesize_answer(state)

    assert "根据检索到的相关段落：" in result["answer"]
    assert result["answer"].count(repeated_header) == 1
    assert "[V1]" in result["answer"]
    assert "营业收入稳步增长" in result["answer"]
    assert result["synthesis"]["citations"][0]["evidence_id"] == "V1"


def _stub_pipeline(*, year: int | None = 2021, company: str = "ACME") -> SimpleNamespace:
    return SimpleNamespace(
        get_document=lambda _doc_id: SimpleNamespace(
            metadata=SimpleNamespace(
                company=company,
                company_aliases=[],
                year=year,
            )
        )
    )


class _StubRetriever:
    def __init__(self, hits: list[tuple[DocumentSegment, float]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._hits = hits or []

    def retrieve(self, question: str, **kwargs: Any) -> list[tuple[DocumentSegment, float]]:
        self.calls.append({"question": question, **kwargs})
        return list(self._hits)


class _StubOrchestrator:
    def __init__(
        self,
        result: OrchestratedRetrievalResult,
        second_result: OrchestratedRetrievalResult | None = None,
    ) -> None:
        self.results = [result, second_result or result]
        self.calls = 0
        self.kwargs_calls: list[dict[str, Any]] = []

    def retrieve(self, question: str, **kwargs: Any) -> OrchestratedRetrievalResult:
        self.kwargs_calls.append({"question": question, **kwargs})
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def test_empty_first_retrieve_triggers_second_retriever_pass() -> None:
    second_segment = DocumentSegment(
        segment_id="seg-second",
        document_id="doc-1",
        position=1,
        content=" complementary MD&A evidence for revenue growth.",
    )
    retriever = _StubRetriever(hits=[(second_segment, 0.81)])
    orchestrator = _StubOrchestrator(
        OrchestratedRetrievalResult(
            analysis=QueryAnalysis(intent="semantic", routes=["vector"]),
            vector_hits=[],
            metrics=[],
            calculations=[],
            graph_paths=[],
            warnings=[],
        )
    )
    service = ResearchService(
        document_pipeline_service=_stub_pipeline(),  # type: ignore[arg-type]
        retriever=retriever,  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
    )

    result = service._run_retrieval(
        {
            "doc_id": "doc-1",
            "question": "Why did revenue grow?",
            "top_k": 3,
            "company_id": "acme",
        }
    )

    assert orchestrator.calls == 2
    assert len(retriever.calls) == 1
    assert any("Second retrieve" in warning for warning in result["warnings"])
    assert result["hits"][0]["segment_id"] == "seg-second"
    assert result["second_retrieve_done"] is True
    assert result["retrieval_passes"] == 2
    assert retriever.calls[0]["years"] is None
    assert result["second_retrieval_plan"]["budget"] == 1
    assert result["second_retrieval_plan"]["routes"] == ["vector"]
    assert result["retrieval_diagnostics"][1]["new_vector_hits"] == 1


def test_insufficient_metrics_triggers_second_retrieve() -> None:
    first = DocumentSegment(
        segment_id="seg-ocf",
        document_id="doc-1",
        position=1,
        content="经营活动产生的现金流量净额同比改善。",
    )
    second = DocumentSegment(
        segment_id="seg-revenue",
        document_id="doc-1",
        position=2,
        content="2021年营业收入增长主要来自软件业务。",
    )
    retriever = _StubRetriever(hits=[(second, 0.8)])
    orchestrator = _StubOrchestrator(
        OrchestratedRetrievalResult(
            analysis=QueryAnalysis(
                intent="hybrid",
                routes=["vector", "sql"],
                metric_keys=["revenue"],
                years=[2021],
                section_hints=["management_discussion"],
            ),
            vector_hits=[(first, 0.9)],
            metrics=[],
            calculations=[],
            graph_paths=[],
            warnings=[],
        )
    )
    service = ResearchService(
        document_pipeline_service=_stub_pipeline(),  # type: ignore[arg-type]
        retriever=retriever,  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
    )

    result = service._run_retrieval(
        {
            "doc_id": "doc-1",
            "question": "2021年营业收入为什么增长？",
            "top_k": 3,
            "company_id": "acme",
        }
    )

    assert any("insufficient metrics" in warning for warning in result["warnings"])
    assert retriever.calls[0]["section_hints"] == []
    assert retriever.calls[0]["metric_keys"] == ["revenue"]
    assert {hit["segment_id"] for hit in result["hits"]} >= {"seg-ocf", "seg-revenue"}


def test_structured_metric_evidence_does_not_trigger_vector_retry() -> None:
    metric = FinancialMetricObservation(
        company_id="acme",
        company="ACME",
        document_id="doc-1",
        document_year=2021,
        metric_key="revenue",
        period="2021",
        period_year=2021,
        value=144,
        unit="millions",
        currency="USD",
    )
    orchestrator = _StubOrchestrator(
        OrchestratedRetrievalResult(
            analysis=QueryAnalysis(
                intent="structured",
                routes=["sql"],
                metric_keys=["revenue"],
                years=[2021],
                section_hints=["financial_statement"],
            ),
            vector_hits=[],
            metrics=[metric],
            calculations=[],
            graph_paths=[],
            warnings=[],
        )
    )
    retriever = _StubRetriever(hits=[])
    service = ResearchService(
        document_pipeline_service=_stub_pipeline(),  # type: ignore[arg-type]
        retriever=retriever,  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
    )

    result = service._run_retrieval(
        {
            "doc_id": "doc-1",
            "question": "What was 2021 revenue?",
            "top_k": 3,
            "company_id": "acme",
        }
    )

    assert orchestrator.calls == 1
    assert retriever.calls == []
    assert result["second_retrieve_done"] is False
    assert result["second_retrieval_plan"] is None


def test_second_retrieve_replaces_full_first_pass_with_targeted_evidence() -> None:
    first_hits = [
        (
            DocumentSegment(
                segment_id=f"seg-first-{index}",
                document_id="doc-1",
                position=index,
                content="General company disclosure without the requested metric.",
            ),
            0.9 - index * 0.1,
        )
        for index in range(3)
    ]
    targeted = DocumentSegment(
        segment_id="seg-targeted",
        document_id="doc-1",
        position=10,
        content="Revenue increased because product demand improved.",
    )
    retriever = _StubRetriever(hits=[(targeted, 0.7)])
    orchestrator = _StubOrchestrator(
        OrchestratedRetrievalResult(
            analysis=QueryAnalysis(
                intent="hybrid",
                routes=["vector", "sql"],
                metric_keys=["revenue"],
            ),
            vector_hits=first_hits,
            metrics=[],
            calculations=[],
            graph_paths=[],
            warnings=[],
        )
    )
    service = ResearchService(
        document_pipeline_service=_stub_pipeline(),  # type: ignore[arg-type]
        retriever=retriever,  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
    )

    result = service._run_retrieval(
        {
            "doc_id": "doc-1",
            "question": "Why did revenue increase?",
            "top_k": 3,
            "company_id": "acme",
        }
    )

    assert result["second_retrieve_done"] is True
    assert result["hits"][0]["segment_id"] == "seg-targeted"
    assert len(result["hits"]) == 3


def test_second_retrieve_runs_full_orchestrator_and_merges_all_channels() -> None:
    general = DocumentSegment(
        segment_id="seg-general",
        document_id="doc-1",
        position=1,
        content="General company overview without financial figures.",
    )
    targeted = DocumentSegment(
        segment_id="seg-targeted",
        document_id="doc-1",
        position=10,
        content="2021 revenue increased because demand improved.",
    )
    metric = FinancialMetricObservation(
        company_id="acme",
        company="ACME",
        document_id="doc-1",
        document_year=2021,
        metric_key="revenue",
        period="2021",
        period_year=2021,
        value=144,
        unit="millions",
        currency="USD",
    )
    first_result = OrchestratedRetrievalResult(
        analysis=QueryAnalysis(
            intent="hybrid",
            routes=["vector", "sql", "graph"],
            metric_keys=["revenue"],
            years=[2021],
        ),
        vector_hits=[(general, 0.75)],
        metrics=[],
        calculations=[],
        graph_paths=[],
        warnings=[],
    )
    second_result = OrchestratedRetrievalResult(
        analysis=first_result.analysis,
        vector_hits=[(targeted, 0.88)],
        metrics=[metric],
        calculations=[],
        graph_paths=[GraphPath(path_id="path:revenue", summary="ACME reports revenue", score=0.9)],
        warnings=[],
    )
    retriever = _StubRetriever(hits=[])
    orchestrator = _StubOrchestrator(first_result, second_result)
    service = ResearchService(
        document_pipeline_service=_stub_pipeline(),  # type: ignore[arg-type]
        retriever=retriever,  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
    )

    result = service._run_retrieval(
        {
            "doc_id": "doc-1",
            "question": "Why did 2021 revenue increase?",
            "top_k": 3,
            "company_id": "acme",
        }
    )

    assert orchestrator.calls == 2
    assert retriever.calls == []
    assert result["hits"][0]["segment_id"] == "seg-targeted"
    assert result["metrics"][0]["metric_key"] == "revenue"
    assert result["graph_paths"][0]["path_id"] == "path:revenue"
    assert result["second_retrieval_plan"]["routes"] == ["vector", "sql", "graph"]
    assert "财务报表" in result["second_retrieval_plan"]["rewritten_query"]
    assert result["retrieval_diagnostics"][1]["new_vector_hits"] == 1
    assert result["retrieval_diagnostics"][1]["new_metrics"] == 1
    assert result["retrieval_diagnostics"][1]["new_graph_paths"] == 1
    assert result["fusion_summary"]["vector_snippet_count"] == 2
    assert result["fusion_summary"]["metric_count"] == 1
    assert result["fusion_summary"]["graph_path_count"] == 1
    assert orchestrator.kwargs_calls[1]["analysis_override"].metric_keys == ["revenue"]


def test_explanation_without_mda_triggers_second_retrieve() -> None:
    statements = [
        DocumentSegment(
            segment_id=f"seg-cfs-{index}",
            document_id="doc-1",
            position=index,
            content="经营活动产生的现金流量净额 373,048,933.00",
            metadata={"section_type": "financial_statement"},
        )
        for index in range(1, 6)
    ]
    mda = DocumentSegment(
        segment_id="seg-mda-ocf",
        document_id="doc-1",
        position=20,
        content="经营活动现金流量净额增长主要由于销售回款加快。",
        metadata={"section_type": "management_discussion"},
    )
    retriever = _StubRetriever(hits=[(mda, 0.84)])
    orchestrator = _StubOrchestrator(
        OrchestratedRetrievalResult(
            analysis=QueryAnalysis(
                intent="hybrid",
                routes=["vector", "sql"],
                metric_keys=["net_cash_from_operating_activities"],
                years=[2020, 2021],
                needs_growth=True,
                section_hints=["financial_statement"],
            ),
            vector_hits=[(segment, 0.9 - index * 0.02) for index, segment in enumerate(statements)],
            metrics=[
                FinancialMetricObservation(
                    company_id="acme",
                    company="ACME",
                    document_id="doc-1",
                    document_year=2021,
                    metric_key="net_cash_from_operating_activities",
                    period="2021",
                    period_year=2021,
                    value=373048933,
                    unit="CNY",
                    currency="CNY",
                )
            ],
            calculations=[],
            graph_paths=[],
            warnings=[],
        )
    )
    service = ResearchService(
        document_pipeline_service=_stub_pipeline(),  # type: ignore[arg-type]
        retriever=retriever,  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
    )

    result = service._run_retrieval(
        {
            "doc_id": "doc-1",
            "question": "2021年经营活动现金流量净额相对2020年为什么增长？",
            "top_k": 5,
            "company_id": "acme",
        }
    )

    assert any("explanation section" in warning for warning in result["warnings"])
    assert result["second_retrieve_done"] is True
    assert retriever.calls[0]["section_hints"] == ["management_discussion"]
    assert result["hits"][0]["segment_id"] == "seg-mda-ocf"
    assert result["hits"][0]["metadata"]["section_type"] == "management_discussion"


def test_pinned_doc_year_mismatch_drops_out_of_year_metrics() -> None:
    orchestrator = _StubOrchestrator(
        OrchestratedRetrievalResult(
            analysis=QueryAnalysis(
                intent="structured",
                routes=["sql"],
                metric_keys=["revenue"],
                years=[2019],
            ),
            vector_hits=[],
            metrics=[
                FinancialMetricObservation(
                    company_id="acme",
                    company="ACME",
                    document_id="doc-1",
                    document_year=2021,
                    metric_key="revenue",
                    period="2021",
                    period_year=2021,
                    value=144,
                    unit="millions",
                    currency="USD",
                )
            ],
            calculations=[],
            graph_paths=[],
            warnings=[],
        )
    )
    retriever = _StubRetriever(hits=[])
    service = ResearchService(
        document_pipeline_service=_stub_pipeline(year=2021),  # type: ignore[arg-type]
        retriever=retriever,  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
    )

    result = service._run_retrieval(
        {
            "doc_id": "doc-1",
            "question": "What was 2019 revenue?",
            "top_k": 3,
            "company_id": "acme",
        }
    )

    assert result["metrics"] == []
    assert any(
        "Pinned document year 2021" in warning and "2019" in warning
        for warning in result["warnings"]
    )
    assert any(
        "do not treat other-year figures as the asked period" in warning
        for warning in result["warnings"]
    )


def test_critic_missing_evidence_reretrieves_once_then_revises() -> None:
    second_segment = DocumentSegment(
        segment_id="seg-risk",
        document_id="doc-1",
        position=2,
        content="Risk factors include customer concentration.",
    )
    retriever = _StubRetriever(hits=[])
    orchestrator = _StubOrchestrator(
        OrchestratedRetrievalResult(
            analysis=QueryAnalysis(
                intent="semantic",
                routes=["vector", "graph"],
                section_hints=["management_discussion"],
            ),
            vector_hits=[(second_segment, 0.77)],
            metrics=[],
            calculations=[],
            graph_paths=[
                GraphPath(
                    path_id="path:risk",
                    summary="ACME has customer concentration risk",
                    score=0.8,
                )
            ],
            warnings=[],
        )
    )

    class _Engine(_FailingGroundedEngine):
        def synthesize(self, **kwargs: Any) -> GroundedSynthesis:
            return GroundedSynthesis(
                answer="revised with extra evidence",
                key_findings=["risk"],
                citations=[],
                confidence=0.4,
                limitations=[],
            )

    service = ResearchService(
        document_pipeline_service=_stub_pipeline(),  # type: ignore[arg-type]
        retriever=retriever,  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
        grounded_engine=_Engine(),  # type: ignore[arg-type]
    )
    state = {
        "doc_id": "doc-1",
        "company_id": "acme",
        "question": "What are the key risks?",
        "top_k": 3,
        "hits": [],
        "query_analysis": {
            "intent": "semantic",
            "routes": ["vector"],
            "section_hints": ["risk_section"],
            "metric_keys": [],
            "years": [],
        },
        "metrics": [],
        "warnings": [],
        "evidence": [],
        "synthesis": GroundedSynthesis(
            answer="draft",
            confidence=0.2,
            limitations=[],
            citations=[],
        ).model_dump(mode="json"),
        "critic": CriticReview(
            passed=False,
            score=0.2,
            issues=[
                {
                    "category": "missing_evidence",
                    "severity": "high",
                    "message": "No supporting snippets.",
                }
            ],
            summary="Need more evidence.",
        ).model_dump(mode="json"),
        "revision_count": 0,
        "max_revisions": 1,
        "second_retrieve_done": False,
        "retrieval_passes": 1,
    }

    result = service._revise_answer(state)

    assert retriever.calls == []
    assert orchestrator.calls == 1
    assert orchestrator.kwargs_calls[0]["analysis_override"].section_hints == [
        "management_discussion"
    ]
    assert result["hits"][0]["segment_id"] == "seg-risk"
    assert result["second_retrieve_done"] is True
    assert result["revision_count"] == 1
    assert result["answer"] == "revised with extra evidence"
    assert result["graph_paths"][0]["path_id"] == "path:risk"
    assert result["retrieval_diagnostics"][0]["new_graph_paths"] == 1
    assert any(
        "Second retrieve: critic missing_evidence" in warning
        for warning in result["warnings"]
    )
    assert result["evidence"]
