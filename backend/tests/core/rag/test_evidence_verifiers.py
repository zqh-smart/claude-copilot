from app.core.llm.evidence_verifiers import (
    verify_citation_entailment,
    verify_entity_scope,
    verify_numeric_claims,
)
from src.claude_copilot.schemas.research import GroundedCitation, GroundedSynthesis


def _synthesis(answer: str, citations: list[GroundedCitation] | None = None) -> GroundedSynthesis:
    return GroundedSynthesis(
        answer=answer,
        key_findings=[],
        citations=citations or [],
        limitations=[],
        confidence=0.8,
    )


def test_verify_numeric_claims_flags_unsupported_large_number() -> None:
    synthesis = _synthesis("2023年营业收入为 999999999 元。")
    evidence = [
        {
            "evidence_id": "S1",
            "source_type": "sql",
            "value": 1_000_000_000,
        }
    ]
    issues = verify_numeric_claims(synthesis, evidence)
    assert any(issue.category == "numeric_mismatch" for issue in issues)


def test_verify_entity_scope_parent_vs_consolidated() -> None:
    metrics = [
        {
            "entity_scope": "consolidated",
            "metric_key": "revenue",
            "period": "2023",
            "value": 100,
        },
        {
            "entity_scope": "parent_company",
            "metric_key": "revenue",
            "period": "2023",
            "value": 80,
        },
    ]
    issues = verify_entity_scope(
        "合并口径营业收入是多少？",
        metrics,
        requested_scope="consolidated",
    )
    assert any(issue.category == "unsupported_claim" for issue in issues)


def test_verify_citation_entailment_requires_marker_in_evidence() -> None:
    synthesis = _synthesis(
        "增长来自主业扩张 [V1]。",
        citations=[
            GroundedCitation(
                evidence_id="V1",
                claim="增长主要来自主营业务扩张与新产品放量",
            )
        ],
    )
    evidence = [{"evidence_id": "V1", "source_type": "vector", "content": "海外收入下降"}]
    issues = verify_citation_entailment(synthesis, evidence)
    assert issues
