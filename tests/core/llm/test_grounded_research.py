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
