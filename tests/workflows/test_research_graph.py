from app.workflows.research.graph import build_research_graph


def test_research_graph_preserves_fusion_summary() -> None:
    fusion = {
        "query_intent": "hybrid",
        "routes": ["vector", "sql"],
        "vector_snippet_count": 2,
        "metric_count": 1,
        "graph_path_count": 0,
        "highlights": ["[结构化] revenue 2021 = 100"],
        "summary": "意图=hybrid，启用通道：语义片段 + 结构化指标。",
    }

    def retrieve(_state: dict) -> dict:
        return {
            "hits": [],
            "query_analysis": {"intent": "hybrid", "routes": ["vector", "sql"]},
            "metrics": [],
            "calculations": [],
            "graph_paths": [],
            "fusion_summary": fusion,
            "warnings": [],
        }

    def synthesize(state: dict) -> dict:
        return {
            "evidence": [],
            "synthesis": {"answer": "preview", "confidence": 0.1, "limitations": []},
            "answer": "preview",
        }

    def critic(_state: dict) -> dict:
        return {
            "critic": {"passed": False, "score": 0.0, "issues": [], "summary": "skip"},
            "grounded": False,
        }

    def revise(state: dict) -> dict:
        return {"revision_count": state.get("revision_count", 0) + 1}

    graph = build_research_graph(retrieve, synthesize, critic, revise)
    result = graph.invoke(
        {
            "doc_id": "doc-1",
            "company_id": "company-1",
            "question": "hybrid question",
            "top_k": 3,
            "revision_count": 0,
            "max_revisions": 0,
        }
    )

    assert result.get("fusion_summary") == fusion
    assert result["answer"] == "preview"
    assert result["critic"]["passed"] is False
    assert result["grounded"] is False
    assert result.get("revision_count", 0) == 0


def test_research_graph_critic_fallback_exits_without_revision() -> None:
    fusion = {"summary": "hybrid routes", "query_intent": "hybrid", "routes": ["vector"]}

    def retrieve(_state: dict) -> dict:
        return {
            "hits": [],
            "query_analysis": {"intent": "hybrid", "routes": ["vector"]},
            "metrics": [],
            "calculations": [],
            "graph_paths": [],
            "fusion_summary": fusion,
            "warnings": [],
        }

    def synthesize(_state: dict) -> dict:
        return {
            "evidence": [{"evidence_id": "S1", "value": 100}],
            "synthesis": {
                "answer": "draft answer",
                "confidence": 0.2,
                "limitations": ["LLM synthesis failed: RuntimeError"],
            },
            "answer": "draft answer",
        }

    def critic(_state: dict) -> dict:
        return {
            "critic": {
                "passed": False,
                "score": 0.0,
                "issues": [
                    {
                        "category": "logic_error",
                        "severity": "high",
                        "message": "Critic execution failed: RuntimeError",
                    }
                ],
                "summary": "Critic failed; answer cannot be marked grounded.",
            },
            "grounded": False,
            "warnings": ["critic failed: boom"],
            "revision_count": 0,
        }

    def revise(_state: dict) -> dict:
        raise AssertionError("revise should not run when max_revisions=0")

    graph = build_research_graph(retrieve, synthesize, critic, revise)
    result = graph.invoke(
        {
            "doc_id": "doc-1",
            "question": "test",
            "top_k": 3,
            "revision_count": 0,
            "max_revisions": 0,
        }
    )

    assert result["answer"] == "draft answer"
    assert result["critic"]["summary"] == "Critic failed; answer cannot be marked grounded."
    assert result["grounded"] is False
    assert result.get("fusion_summary") == fusion
    assert result.get("warnings") == ["critic failed: boom"]
    assert result.get("revision_count", 0) == 0
