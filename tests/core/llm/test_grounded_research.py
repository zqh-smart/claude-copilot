from app.core.llm import GroundedResearchEngine
from app.workflows.research.graph import build_research_graph
from src.claude_copilot.schemas.research import CriticReview, GroundedSynthesis


class SequenceJsonClient:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        assert system_prompt
        assert user_prompt
        return self._responses.pop(0)


def test_graph_paths_are_added_to_grounded_evidence() -> None:
    engine = GroundedResearchEngine(SequenceJsonClient([]))

    evidence = engine.build_evidence(
        {
            "graph_paths": [
                {
                    "path_id": "relationship:risk",
                    "summary": "ACME -[HAS_RISK]-> liquidity_risk",
                    "score": 0.9,
                    "nodes": [
                        {
                            "node_id": "risk:liquidity",
                            "node_type": "risk",
                            "name": "liquidity_risk",
                            "properties": {"evidence": "Liquidity pressure remains."},
                        }
                    ],
                }
            ]
        }
    )

    assert evidence[0]["evidence_id"] == "G1"
    assert evidence[0]["source_type"] == "graph"
    assert evidence[0]["nodes"][0]["node_type"] == "risk"


def test_critic_rejects_draft_without_citations_even_if_model_passes() -> None:
    engine = GroundedResearchEngine(
        SequenceJsonClient(
            [
                {
                    "passed": True,
                    "score": 0.95,
                    "issues": [],
                    "summary": "Looks good.",
                }
            ]
        )
    )
    draft = GroundedSynthesis(
        answer="Net income was 100.",
        key_findings=["Net income was 100."],
        citations=[],
        confidence=0.9,
        limitations=[],
    )
    review = engine.critique(
        question="What was net income?",
        evidence=[{"evidence_id": "S1", "value": 100}],
        synthesis=draft,
    )

    assert review.passed is False
    assert review.score == 0.49
    assert review.issues[-1].category == "missing_evidence"
    assert review.issues[-1].severity == "high"


def test_research_graph_revises_failed_draft_and_rechecks() -> None:
    calls = {"critic": 0}

    def retrieve(_state: dict) -> dict:
        return {"evidence": [{"evidence_id": "S1", "value": 100}]}

    def synthesize(_state: dict) -> dict:
        return {
            "synthesis": {
                "answer": "Net income was 90 [S1].",
                "key_findings": [],
                "citations": [{"evidence_id": "S1", "claim": "Net income was 90."}],
                "confidence": 0.4,
                "limitations": [],
            },
            "answer": "Net income was 90 [S1].",
        }

    def critique(state: dict) -> dict:
        calls["critic"] += 1
        passed = state["answer"] == "Net income was 100 [S1]."
        review = CriticReview(
            passed=passed,
            score=1.0 if passed else 0.2,
            issues=[],
            summary="passed" if passed else "numeric mismatch",
        )
        return {"critic": review.model_dump(mode="json"), "grounded": passed}

    def revise(state: dict) -> dict:
        revised = {
            "answer": "Net income was 100 [S1].",
            "key_findings": ["Net income was 100."],
            "citations": [{"evidence_id": "S1", "claim": "Net income was 100."}],
            "confidence": 0.95,
            "limitations": [],
        }
        return {
            "synthesis": revised,
            "answer": revised["answer"],
            "revision_count": state.get("revision_count", 0) + 1,
        }

    graph = build_research_graph(retrieve, synthesize, critique, revise)
    result = graph.invoke({"revision_count": 0, "max_revisions": 1})

    assert result["answer"] == "Net income was 100 [S1]."
    assert result["grounded"] is True
    assert result["revision_count"] == 1
    assert calls["critic"] == 2


def test_research_graph_stops_after_revision_limit() -> None:
    def retrieve(_state: dict) -> dict:
        return {}

    def synthesize(_state: dict) -> dict:
        return {"answer": "unsupported", "synthesis": {}}

    def critique(_state: dict) -> dict:
        return {
            "critic": {
                "passed": False,
                "score": 0.0,
                "issues": [],
                "summary": "failed",
            },
            "grounded": False,
        }

    def revise(state: dict) -> dict:
        return {"revision_count": state.get("revision_count", 0) + 1}

    graph = build_research_graph(retrieve, synthesize, critique, revise)
    result = graph.invoke({"revision_count": 0, "max_revisions": 1})

    assert result["grounded"] is False
    assert result["revision_count"] == 1


def test_synthesize_sanitizes_unknown_citation_ids() -> None:
    engine = GroundedResearchEngine(
        SequenceJsonClient(
            [
                {
                    "answer": "Industry overview [S1] with graph context [G1].",
                    "key_findings": ["Sector detail [S3]"],
                    "citations": [
                        {"evidence_id": "S1", "claim": "unsupported sql cite"},
                        {"evidence_id": "G1", "claim": "graph path"},
                    ],
                    "confidence": 0.7,
                    "limitations": [],
                }
            ]
        )
    )
    evidence = [
        {
            "evidence_id": "G1",
            "source_type": "graph",
            "summary": "Company operates in semiconductors.",
        }
    ]

    synthesis = engine.synthesize(
        question="What industry is the company in?",
        evidence=evidence,
    )

    assert synthesis.answer == "Industry overview with graph context [G1]."
    assert synthesis.key_findings == ["Sector detail"]
    assert [citation.evidence_id for citation in synthesis.citations] == ["G1"]


def test_synthesize_prefers_calculation_yoy_over_vector_rate() -> None:
    engine = GroundedResearchEngine(
        SequenceJsonClient(
            [
                {
                    "answer": "Revenue grew 34.63% in 2021 [V1].",
                    "key_findings": [],
                    "citations": [{"evidence_id": "V1", "claim": "vector snippet"}],
                    "confidence": 0.8,
                    "limitations": [],
                }
            ]
        )
    )
    evidence = [
        {
            "evidence_id": "V1",
            "source_type": "vector",
            "content": "Revenue increased 34.63% year over year.",
        },
        {
            "evidence_id": "C1",
            "source_type": "calculation",
            "source_id": "revenue",
            "yoy_growth": {"2021": 34.75},
        },
    ]

    synthesis = engine.synthesize(
        question="Why did revenue grow in 2021?",
        evidence=evidence,
    )

    assert "34.75%" in synthesis.answer
    assert "34.63%" not in synthesis.answer
    assert any(citation.evidence_id == "C1" for citation in synthesis.citations)


def test_synthesize_softens_revenue_growth_causation() -> None:
    engine = GroundedResearchEngine(
        SequenceJsonClient(
            [
                {
                    "answer": "营收增长主要原因是加大研发与品牌推广[V1]，增幅34.63%。",
                    "key_findings": [],
                    "citations": [{"evidence_id": "V1", "claim": "drivers"}],
                    "confidence": 0.9,
                    "limitations": [],
                }
            ]
        )
    )
    evidence = [
        {
            "evidence_id": "V1",
            "source_type": "vector",
            "content": "净利润增幅较大与研发投入相关",
        },
        {
            "evidence_id": "C1",
            "source_type": "calculation",
            "source_id": "revenue",
            "yoy_growth": {2021: 0.3475},
        },
    ]
    synthesis = engine.synthesize(
        question="2021年营业收入相对2020年为什么增长？",
        evidence=evidence,
    )
    assert "34.75%" in synthesis.answer
    assert "主要原因" not in synthesis.answer
    assert "因果" in synthesis.answer
    assert any(c.evidence_id == "C1" for c in synthesis.citations)


def test_synthesize_prefers_fractional_yoy_from_orchestrator() -> None:
    """Production MetricCalculation stores YoY as a fraction (0.3475), not percent."""
    engine = GroundedResearchEngine(
        SequenceJsonClient(
            [
                {
                    "answer": "Revenue grew 34.63% in 2021 [V1].",
                    "key_findings": [],
                    "citations": [{"evidence_id": "V1", "claim": "vector"}],
                    "confidence": 0.7,
                    "limitations": [],
                }
            ]
        )
    )
    evidence = [
        {
            "evidence_id": "V1",
            "source_type": "vector",
            "content": "Revenue grew 34.63%",
        },
        {
            "evidence_id": "C1",
            "source_type": "calculation",
            "source_id": "revenue",
            "yoy_growth": {2021: 0.3475},
        },
    ]
    synthesis = engine.synthesize(
        question="What was 2021 revenue growth vs 2020?",
        evidence=evidence,
    )
    assert "34.75%" in synthesis.answer
    assert "34.63%" not in synthesis.answer
    assert any(citation.evidence_id == "C1" for citation in synthesis.citations)


def test_synthesize_includes_available_evidence_ids_in_prompt() -> None:
    captured: dict[str, str] = {}

    class CaptureClient:
        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            captured["user_prompt"] = user_prompt
            return {
                "answer": "Done [G1].",
                "key_findings": [],
                "citations": [{"evidence_id": "G1", "claim": "graph"}],
                "confidence": 0.9,
                "limitations": [],
            }

    engine = GroundedResearchEngine(CaptureClient())
    evidence = [{"evidence_id": "G1", "source_type": "graph", "summary": "path"}]

    engine.synthesize(question="Industry?", evidence=evidence)

    assert "Available evidence IDs: G1" in captured["user_prompt"]
