from app.workflows.risk.graph import (
    _extract_has_risk_findings,
    build_risk_graph,
)


def test_extract_has_risk_findings_deduplicates_paths() -> None:
    graph_paths = [
        {
            "path_id": "p1",
            "summary": "ACME -[HAS_RISK]-> market_risk",
            "nodes": [
                {"node_id": "company:acme", "node_type": "company", "name": "ACME"},
                {
                    "node_id": "risk:market",
                    "node_type": "risk",
                    "name": "market_risk",
                    "properties": {"risk_type": "market_risk"},
                },
            ],
            "relationships": [
                {
                    "relationship_id": "rel:1",
                    "relationship_type": "HAS_RISK",
                    "source_node_id": "company:acme",
                    "target_node_id": "risk:market",
                    "evidence_text": "市场波动可能导致收入不确定",
                }
            ],
        }
    ]

    findings = _extract_has_risk_findings(graph_paths)

    assert len(findings) == 1
    assert findings[0]["risk_type"] == "market_risk"
    assert findings[0]["relation"] == "HAS_RISK"
    assert "市场波动" in findings[0]["evidence"]


def test_risk_graph_summarize_without_llm() -> None:
    def retrieve(_state: dict) -> dict:
        return {
            "graph_paths": [
                {
                    "path_id": "p1",
                    "summary": "ACME -[HAS_RISK]-> liquidity_risk",
                    "nodes": [
                        {"node_id": "company:acme", "node_type": "company", "name": "ACME"},
                        {
                            "node_id": "risk:liquidity",
                            "node_type": "risk",
                            "name": "liquidity_risk",
                            "properties": {},
                        },
                    ],
                    "relationships": [
                        {
                            "relationship_id": "rel:1",
                            "relationship_type": "HAS_RISK",
                            "source_node_id": "company:acme",
                            "target_node_id": "risk:liquidity",
                            "evidence_text": "流动性风险",
                        }
                    ],
                }
            ],
            "hits": [
                {
                    "segment_id": "seg-1",
                    "score": 0.9,
                    "content": "公司面临的主要市场风险包括行业竞争加剧。",
                    "metadata": {"section_type": "risk_disclosure"},
                }
            ],
            "warnings": [],
        }

    compiled = build_risk_graph(retrieve_fn=retrieve)
    result = compiled.invoke(
        {
            "doc_id": "doc-1",
            "company_id": "acme",
            "question": "公司面临哪些市场风险？",
            "top_k": 5,
        }
    )

    assert result["risk_findings"]
    assert result["risk_findings"][0]["risk_type"] == "liquidity_risk"
    assert "HAS_RISK" in result["answer"]
    assert "liquidity_risk" in result["answer"]
    assert "市场风险" in result["answer"]
