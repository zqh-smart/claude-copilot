from __future__ import annotations

from typing import Any

from app.api.services.research_service import ResearchService
from app.core.rag import LocalRetriever
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService
from src.claude_copilot.schemas.research import CriticReview, GroundedSynthesis


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
