"""Deterministic financial evidence checks (independent of LLM critic)."""

from __future__ import annotations

import re
from typing import Any

from src.claude_copilot.schemas.research import CriticIssue, GroundedSynthesis

_NUMERIC_TOKEN = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\d)"
)


def _normalize_number(text: str) -> float | None:
    cleaned = text.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _numbers_in_text(text: str) -> list[float]:
    values: list[float] = []
    for match in _NUMERIC_TOKEN.findall(text):
        parsed = _normalize_number(match)
        if parsed is not None:
            values.append(parsed)
    return values


def verify_numeric_claims(
    synthesis: GroundedSynthesis,
    evidence: list[dict[str, Any]],
    *,
    relative_tolerance: float = 0.02,
) -> list[CriticIssue]:
    """Flag answer numbers that do not appear in SQL/calculation evidence."""
    authoritative: list[float] = []
    for item in evidence:
        if item.get("source_type") not in {"sql", "calculation"}:
            continue
        value = item.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            authoritative.append(float(value))
        yearly = (item.get("yearly_values") or {}) if isinstance(item, dict) else {}
        for raw in yearly.values():
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                authoritative.append(float(raw))
        yoy = (item.get("yoy_growth") or {}) if isinstance(item, dict) else {}
        for raw in yoy.values():
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                authoritative.append(float(raw))

    if not authoritative:
        return []

    answer_numbers = _numbers_in_text(synthesis.answer)
    if not answer_numbers:
        return []

    issues: list[CriticIssue] = []
    for number in answer_numbers:
        if number < 1000:
            continue
        matched = any(
            abs(number - auth) <= max(1.0, abs(auth) * relative_tolerance)
            for auth in authoritative
        )
        if not matched:
            issues.append(
                CriticIssue(
                    category="numeric_mismatch",
                    severity="high",
                    message=(
                        f"Answer number {number:g} is not supported by SQL/calculation "
                        "evidence within tolerance."
                    ),
                )
            )
            break
    return issues


def verify_entity_scope(
    question: str,
    metrics: list[dict[str, Any]],
    *,
    requested_scope: str | None,
) -> list[CriticIssue]:
    if not metrics or requested_scope not in {"consolidated", "parent_company"}:
        return []
    scopes = {
        str(item.get("entity_scope") or "unknown")
        for item in metrics
        if item.get("metric_key") and item.get("period")
    }
    if len(scopes) <= 1:
        return []
    conflicting = scopes - {requested_scope, "unknown"}
    if not conflicting:
        return []
    return [
        CriticIssue(
            category="unsupported_claim",
            severity="high",
            message=(
                f"Entity scope conflict: question expects {requested_scope} but "
                f"metrics include {sorted(conflicting)}."
            ),
        )
    ]


def verify_citation_entailment(
    synthesis: GroundedSynthesis,
    evidence: list[dict[str, Any]],
) -> list[CriticIssue]:
    """Lightweight check: cited claims should overlap evidence text or metric values."""
    by_id = {item["evidence_id"]: item for item in evidence if item.get("evidence_id")}
    issues: list[CriticIssue] = []
    for citation in synthesis.citations:
        item = by_id.get(citation.evidence_id)
        if item is None:
            continue
        claim = citation.claim.casefold()
        if not claim.strip():
            continue
        if item.get("source_type") == "sql":
            metric_key = str(item.get("metric_key") or "").casefold()
            value = str(item.get("value") or "")
            if metric_key not in claim and value not in claim:
                issues.append(
                    CriticIssue(
                        category="citation_error",
                        severity="medium",
                        message=(
                            f"Citation {citation.evidence_id} claim does not mention "
                            "the structured metric/value."
                        ),
                        evidence_ids=[citation.evidence_id],
                    )
                )
            continue
        content = str(item.get("content") or "").casefold()
        if len(claim) >= 12 and claim[:40] not in content and not any(
            token in content for token in claim.split()[:6] if len(token) >= 4
        ):
            issues.append(
                CriticIssue(
                    category="citation_error",
                    severity="low",
                    message=(
                        f"Citation {citation.evidence_id} claim may not be entailed "
                        "by the evidence snippet."
                    ),
                    evidence_ids=[citation.evidence_id],
                )
            )
    return issues


def merge_verifier_issues(
    review_issues: list[CriticIssue],
    extra: list[CriticIssue],
) -> list[CriticIssue]:
    seen = {(issue.category, issue.message) for issue in review_issues}
    merged = list(review_issues)
    for issue in extra:
        key = (issue.category, issue.message)
        if key in seen:
            continue
        seen.add(key)
        merged.append(issue)
    return merged
