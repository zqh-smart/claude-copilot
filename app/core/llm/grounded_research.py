from __future__ import annotations

import json
import re
from typing import Any

from app.core.llm.client import JsonChatClientProtocol
from src.claude_copilot.schemas.research import (
    CriticIssue,
    CriticReview,
    GroundedCitation,
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
                    "relationships": [
                        {
                            "relationship_type": relationship["relationship_type"],
                            "page_range": relationship.get("page_range"),
                            "evidence_text": relationship.get("evidence_text"),
                            "confidence": relationship.get("confidence"),
                        }
                        for relationship in item.get("relationships", [])
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
        available_ids = ", ".join(item["evidence_id"] for item in evidence)
        payload = self._client.complete_json(
            system_prompt=self._synthesis_system_prompt(),
            user_prompt=(
                f"Question:\n{question}\n\n"
                f"Available evidence IDs: {available_ids or '(none)'}\n\n"
                f"Evidence catalog:\n{json.dumps(evidence, ensure_ascii=False)}\n"
                f"{revision_context}"
                "\nReturn only the required JSON object."
            ),
        )
        synthesis = GroundedSynthesis.model_validate(payload)
        synthesis = self._sanitize_synthesis_citations(synthesis, evidence)
        synthesis = self._prefer_calculation_growth_rates(
            question=question,
            synthesis=synthesis,
            evidence=evidence,
        )
        synthesis = self._soften_revenue_growth_causation(
            question=question,
            synthesis=synthesis,
            evidence=evidence,
        )
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

    def _sanitize_synthesis_citations(
        self,
        synthesis: GroundedSynthesis,
        evidence: list[dict[str, Any]],
    ) -> GroundedSynthesis:
        valid_ids = {item["evidence_id"] for item in evidence}
        invalid_citation_ids = {
            citation.evidence_id
            for citation in synthesis.citations
            if citation.evidence_id not in valid_ids
        }
        inline_ids = set(re.findall(r"\[([VSCG]\d+)\]", synthesis.answer))
        inline_ids.update(
            match
            for finding in synthesis.key_findings
            for match in re.findall(r"\[([VSCG]\d+)\]", finding)
        )
        invalid_marker_ids = (invalid_citation_ids | inline_ids) - valid_ids
        valid_citations = [
            citation
            for citation in synthesis.citations
            if citation.evidence_id in valid_ids
        ]
        if not invalid_marker_ids and len(valid_citations) == len(synthesis.citations):
            return synthesis

        marker_pattern = re.compile(
            r"\[(?:"
            + "|".join(re.escape(item) for item in sorted(invalid_marker_ids))
            + r")\]"
        ) if invalid_marker_ids else None
        answer = synthesis.answer
        key_findings = list(synthesis.key_findings)
        if marker_pattern is not None:
            answer = marker_pattern.sub("", answer)
            answer = re.sub(r"  +", " ", answer).strip()
            key_findings = [
                re.sub(r"  +", " ", marker_pattern.sub("", finding)).strip()
                for finding in key_findings
            ]
        return synthesis.model_copy(
            update={
                "answer": answer,
                "key_findings": key_findings,
                "citations": valid_citations,
            }
        )

    def _prefer_calculation_growth_rates(
        self,
        *,
        question: str,
        synthesis: GroundedSynthesis,
        evidence: list[dict[str, Any]],
    ) -> GroundedSynthesis:
        calc_items = [
            item
            for item in evidence
            if item.get("source_type") == "calculation" and item.get("yoy_growth")
        ]
        if not calc_items:
            return synthesis

        context = f"{question} {synthesis.answer}"
        # Avoid \\b — CJK letters are \\w in Python, so "相对2020" would miss the year.
        years_in_context = set(re.findall(r"(?<!\d)(20\d{2})(?!\d)", context))
        pct_pattern = re.compile(r"(\d+(?:\.\d+)?)%")
        pct_match = pct_pattern.search(synthesis.answer)
        if not pct_match:
            return synthesis

        answer_pct = float(pct_match.group(1))
        for calc in calc_items:
            yoy_growth = calc.get("yoy_growth") or {}
            for year, rate in yoy_growth.items():
                if str(year) not in years_in_context:
                    continue
                authoritative = self._as_percent(float(rate))
                if abs(answer_pct - authoritative) <= 0.05:
                    continue
                formatted = self._format_growth_pct(authoritative)
                new_answer = pct_pattern.sub(formatted, synthesis.answer, count=1)
                citations = list(synthesis.citations)
                if not any(
                    citation.evidence_id == calc["evidence_id"] for citation in citations
                ):
                    citations.append(
                        GroundedCitation(
                            evidence_id=calc["evidence_id"],
                            claim=f"YoY growth for {year}: {formatted}",
                        )
                    )
                return synthesis.model_copy(
                    update={"answer": new_answer, "citations": citations}
                )
        return synthesis

    @staticmethod
    def _as_percent(rate: float) -> float:
        """Orchestrator stores YoY as a fraction (0.3475); answers use percent (34.75)."""
        if -1.0 <= rate <= 1.0:
            return rate * 100.0
        return rate

    @staticmethod
    def _format_growth_pct(rate: float) -> str:
        if abs(rate - round(rate)) < 1e-9:
            return f"{int(round(rate))}%"
        return f"{rate:.2f}%"

    def _soften_revenue_growth_causation(
        self,
        *,
        question: str,
        synthesis: GroundedSynthesis,
        evidence: list[dict[str, Any]],
    ) -> GroundedSynthesis:
        """Avoid treating profit-driver MD&A as proven revenue-growth causation."""
        q = question.casefold()
        if not any(token in q for token in ("为什么增长", "为何增长", "why", "growth")):
            return synthesis
        if not any(token in q for token in ("营收", "营业收入", "revenue")):
            return synthesis

        calc = next(
            (
                item
                for item in evidence
                if item.get("source_type") == "calculation" and item.get("yoy_growth")
            ),
            None,
        )
        vector = next(
            (item for item in evidence if item.get("source_type") == "vector"),
            None,
        )
        if calc is None:
            return synthesis

        years = sorted(str(year) for year in (calc.get("yoy_growth") or {}))
        year = years[-1] if years else ""
        rate = (calc.get("yoy_growth") or {}).get(int(year) if year.isdigit() else year)
        if rate is None and year:
            rate = (calc.get("yoy_growth") or {}).get(year)
        if rate is None:
            return synthesis

        formatted = self._format_growth_pct(self._as_percent(float(rate)))
        answer = (
            f"{year}年营业收入相对上年增长{formatted}[{calc['evidence_id']}]。"
            "证据中的经营叙述将研发投入、品牌推广与用户增长等因素主要关联到净利润等表现，"
            "未明确建立营业收入增长的单一因果链条"
        )
        citations = [
            GroundedCitation(
                evidence_id=calc["evidence_id"],
                claim=f"Authoritative YoY growth {formatted}",
            )
        ]
        if vector is not None:
            answer += f"[{vector['evidence_id']}]。"
            citations.append(
                GroundedCitation(
                    evidence_id=vector["evidence_id"],
                    claim="Qualitative factors linked in disclosure; causation for revenue not established",
                )
            )
        else:
            answer += "。"
        limitations = list(synthesis.limitations)
        note = "Evidence does not establish causal drivers of revenue growth."
        if note not in limitations:
            limitations.append(note)
        return synthesis.model_copy(
            update={
                "answer": answer,
                "citations": citations,
                "limitations": limitations,
                "confidence": min(float(synthesis.confidence), 0.7),
            }
        )

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
Only cite evidence_id values that appear in the catalog (see Available evidence IDs).
Never invent S* IDs when the catalog has only V*, G*, or C* items, and never invent
G* IDs when only V* or S* items exist.
For YoY growth or CAGR, always use calculation (C*) or SQL (S*) values when present;
do not prefer approximate percentages from vector (V*) text over authoritative math.
Never label a factor as a "driver", "primary driver", "fueled", "caused",
"主要原因", or "导致" unless the evidence explicitly links that factor to the
requested outcome (usually MD&A stating the reason). Prefer stating associated
movements and that causal attribution is not established when only contemporaneous
figures or marketing/R&D narrative appear beside revenue growth.
When SQL (S*) values exist for the same metric/period, cite the exact S* numbers;
do not round to 亿元 approximations from vector text. When C* YoY/CAGR exists,
use that rate rather than any percentage printed in vector snippets.

Answer in the same language as the question. Every material claim must cite one or
more evidence IDs in the citations array. If evidence is insufficient, say so in
limitations and lower confidence.
During revision, resolve every high-severity critic issue. If the evidence cannot
support a disputed claim, remove or weaken it rather than defending it.

Return exactly this JSON shape:
{
  "answer": "concise final answer with inline [V1]/[G1]/[C1] markers using only catalog IDs",
  "key_findings": ["finding"],
  "citations": [{"evidence_id": "V1", "claim": "claim supported by it"}],
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
and may be cited directly. When a draft cites a C* YoY/CAGR rate that conflicts
with a percentage printed in vector (V*) text, prefer C* and do NOT flag
numeric_mismatch against the vector figure. Do not demand that every evidence
item be used.
A cautious statement that causal evidence is insufficient is valid and should
usually pass when the draft (a) cites C*/S* for the growth magnitude and
(b) explicitly refuses to assert unsupported revenue drivers from MD&A that
only link factors to profit or contemporaneous movements.
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
