from __future__ import annotations

import json
from typing import Any

from app.core.llm.client import JsonChatClientProtocol
from src.claude_copilot.schemas.research import (
    CriticIssue,
    CriticReview,
    GroundedSynthesis,
)


class GroundedResearchEngine:
    def __init__(self, client: JsonChatClientProtocol) -> None:
        self._client = client

    def build_evidence(self, state: dict) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for index, hit in enumerate(state.get("hits", []), start=1):
            evidence.append(
                {
                    "evidence_id": f"V{index}",
                    "source_type": "vector",
                    "source_id": hit["segment_id"],
                    "score": hit["score"],
                    "content": hit["content"][:1800],
                }
            )
        for index, item in enumerate(state.get("metrics", [])[:30], start=1):
            evidence.append(
                {
                    "evidence_id": f"S{index}",
                    "source_type": "sql",
                    "source_id": item.get("source_table_id"),
                    "metric_key": item["metric_key"],
                    "period": item["period"],
                    "value": item["value"],
                    "unit": item.get("unit"),
                    "currency": item.get("currency"),
                    "page_range": item.get("page_range"),
                }
            )
        for index, item in enumerate(state.get("calculations", []), start=1):
            evidence.append(
                {
                    "evidence_id": f"C{index}",
                    "source_type": "calculation",
                    "source_id": item["metric_key"],
                    "yearly_values": item.get("yearly_values", {}),
                    "yoy_growth": item.get("yoy_growth", {}),
                    "cagr": item.get("cagr"),
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
                    "nodes": [
                        {
                            "node_id": node["node_id"],
                            "node_type": node["node_type"],
                            "name": node["name"],
                            "properties": node.get("properties", {}),
                        }
                        for node in item.get("nodes", [])
                    ],
                }
            )
        return evidence

    def synthesize(
        self,
        *,
        question: str,
        evidence: list[dict[str, Any]],
        previous_draft: GroundedSynthesis | None = None,
        critic_review: CriticReview | None = None,
    ) -> GroundedSynthesis:
        revision_context = ""
        if previous_draft is not None and critic_review is not None:
            revision_context = (
                "\nPrevious draft:\n"
                f"{previous_draft.model_dump_json()}\n"
                "Critic review that must be resolved:\n"
                f"{critic_review.model_dump_json()}\n"
            )
        payload = self._client.complete_json(
            system_prompt=self._synthesis_system_prompt(),
            user_prompt=(
                f"Question:\n{question}\n\n"
                f"Evidence catalog:\n{json.dumps(evidence, ensure_ascii=False)}\n"
                f"{revision_context}"
                "\nReturn only the required JSON object."
            ),
        )
        synthesis = GroundedSynthesis.model_validate(payload)
        self._ensure_citations_exist(synthesis, evidence)
        return synthesis

    def critique(
        self,
        *,
        question: str,
        evidence: list[dict[str, Any]],
        synthesis: GroundedSynthesis,
    ) -> CriticReview:
        payload = self._client.complete_json(
            system_prompt=self._critic_system_prompt(),
            user_prompt=(
                f"Question:\n{question}\n\n"
                f"Evidence catalog:\n{json.dumps(evidence, ensure_ascii=False)}\n\n"
                f"Draft:\n{synthesis.model_dump_json()}\n\n"
                "Return only the required JSON object."
            ),
        )
        review = CriticReview.model_validate(payload)
        return self._apply_deterministic_checks(review, synthesis, evidence)

    def _ensure_citations_exist(
        self,
        synthesis: GroundedSynthesis,
        evidence: list[dict[str, Any]],
    ) -> None:
        valid_ids = {item["evidence_id"] for item in evidence}
        invalid = [
            citation.evidence_id
            for citation in synthesis.citations
            if citation.evidence_id not in valid_ids
        ]
        if invalid:
            raise ValueError(f"Synthesis cited unknown evidence IDs: {sorted(set(invalid))}")

    def _apply_deterministic_checks(
        self,
        review: CriticReview,
        synthesis: GroundedSynthesis,
        evidence: list[dict[str, Any]],
    ) -> CriticReview:
        valid_ids = {item["evidence_id"] for item in evidence}
        invalid_ids = sorted(
            {
                citation.evidence_id
                for citation in synthesis.citations
                if citation.evidence_id not in valid_ids
            }
        )
        issues = list(review.issues)
        if invalid_ids:
            issues.append(
                CriticIssue(
                    category="citation_error",
                    severity="high",
                    message=f"Unknown evidence IDs: {invalid_ids}",
                    evidence_ids=invalid_ids,
                )
            )
        if evidence and not synthesis.citations:
            issues.append(
                CriticIssue(
                    category="missing_evidence",
                    severity="high",
                    message="Draft contains no citations despite available evidence.",
                )
            )
        has_high_issue = any(issue.severity == "high" for issue in issues)
        return review.model_copy(
            update={
                "passed": bool(review.passed and not has_high_issue),
                "issues": issues,
                "score": min(review.score, 0.49) if has_high_issue else review.score,
            }
        )

    def _synthesis_system_prompt(self) -> str:
        return """
You are a grounded financial research synthesizer.
Use only the supplied evidence catalog. Never invent facts, causes, values, dates,
units, currencies, or citations. SQL evidence is authoritative for exact numbers;
calculation evidence is authoritative for YoY and CAGR. Vector evidence may support
qualitative explanations but not unsupported causal claims.
Never label a factor as a "driver", "primary driver", "fueled", or "caused"
unless the evidence explicitly links that factor to the requested outcome.
When evidence only shows contemporaneous changes, describe them as associated
movements and state that attribution is not established.

Answer in the same language as the question. Every material claim must cite one or
more evidence IDs in the citations array. If evidence is insufficient, say so in
limitations and lower confidence.
During revision, resolve every high-severity critic issue. If the evidence cannot
support a disputed claim, remove or weaken it rather than defending it.

Return exactly this JSON shape:
{
  "answer": "concise final answer with inline [S1]/[V1]/[C1] markers",
  "key_findings": ["finding"],
  "citations": [{"evidence_id": "S1", "claim": "claim supported by it"}],
  "confidence": 0.0,
  "limitations": ["limitation"]
}
""".strip()

    def _critic_system_prompt(self) -> str:
        return """
You are an independent financial answer critic. Audit the draft against the
evidence catalog. Check every exact number, year, unit, currency, calculation,
causal statement, and citation. Do not reward plausible but unsupported claims.
C* calculation evidence is authoritative for the deterministic math it contains
and may be cited directly. Do not demand that every evidence item be used.
A cautious statement that causal evidence is insufficient is valid unless an
evidence item explicitly states the causal link; contemporaneous revenue, expense,
or gain data alone does not prove causation.
Set passed=false for any high-severity issue. Do not rewrite the answer.

Return exactly this JSON shape:
{
  "passed": true,
  "score": 0.0,
  "issues": [
    {
      "category": "unsupported_claim|numeric_mismatch|citation_error|logic_error|missing_evidence",
      "severity": "low|medium|high",
      "message": "specific problem",
      "evidence_ids": ["S1"]
    }
  ],
  "summary": "short audit summary"
}
""".strip()
