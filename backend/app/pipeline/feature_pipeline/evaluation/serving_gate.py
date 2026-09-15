"""L2 serving-track gate: decide what may enter Postgres / Qdrant / Neo4j."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.pipeline.feature_pipeline.evaluation.source_grounding import SourceGroundingService
from app.pipeline.feature_pipeline.evaluation.stage_scorecard import StageScorecardService
from src.claude_copilot.schemas.document import DocumentSegment, FinancialMetricFact, ParsedDocument


@dataclass
class ServingGateResult:
    allow_metric_serving: bool
    allow_segment_serving: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    grounded_fact_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ServingGateService:
    """Apply evaluation_system.md L2 gates before serving-track writes."""

    def __init__(
        self,
        *,
        min_source_grounding_rate: float = 0.95,
        max_implausible_period_ratio: float = 0.0,
        min_statements_with_metrics_ratio: float = 1.0,
        require_company: bool = True,
        require_year: bool = True,
    ) -> None:
        self._min_source_grounding_rate = min_source_grounding_rate
        self._max_implausible_period_ratio = max_implausible_period_ratio
        self._min_statements_with_metrics_ratio = min_statements_with_metrics_ratio
        self._require_company = require_company
        self._require_year = require_year
        self._scorecard = StageScorecardService()
        self._grounding = SourceGroundingService()

    def evaluate(
        self,
        document: ParsedDocument,
        *,
        expectations: dict[str, Any] | None = None,
        scorecard: dict[str, Any] | None = None,
    ) -> ServingGateResult:
        expectations = expectations or {}
        gate_cfg = expectations.get("serving_gate") or {}
        min_grounding = float(gate_cfg.get("min_source_grounding_rate", self._min_source_grounding_rate))
        max_implausible = float(
            gate_cfg.get("max_implausible_period_ratio", self._max_implausible_period_ratio)
        )
        min_stmt_metrics = float(
            gate_cfg.get("min_statements_with_metrics_ratio", self._min_statements_with_metrics_ratio)
        )

        scorecard = scorecard or self._scorecard.build_from_document(
            document,
            expectations=expectations,
        )
        summary = dict(scorecard.get("summary_scores") or {})
        schema_stage = scorecard.get("stages", {}).get("schema", {})
        failures: list[str] = []
        warnings: list[str] = []

        company = document.metadata.company or (
            document.financial_schema.company if document.financial_schema else None
        )
        year = document.metadata.year or (
            document.financial_schema.year if document.financial_schema else None
        )
        if self._require_company and not company:
            failures.append("missing_company")
        if self._require_year and year is None:
            failures.append("missing_year")

        fact_count = int(schema_stage.get("metric_fact_count") or 0)
        grounding_rate = schema_stage.get("source_grounding_rate")
        implausible = schema_stage.get("implausible_period_ratio")
        stmt_metrics_ratio = schema_stage.get("statements_with_metrics_ratio")
        core_match = schema_stage.get("core_metric_exact_match")

        filled_core = self._has_filled_core_metrics(expectations)
        if filled_core:
            if core_match is None:
                failures.append("core_metric_exact_match_unavailable")
            elif float(core_match) < 1.0 - 1e-9:
                failures.append(f"core_metric_exact_match<{1.0}:{core_match}")

        if fact_count > 0:
            if grounding_rate is None or float(grounding_rate) + 1e-9 < min_grounding:
                failures.append(
                    f"source_grounding_rate<{min_grounding}:{grounding_rate}"
                )
            if implausible is not None and float(implausible) - 1e-9 > max_implausible:
                failures.append(
                    f"implausible_period_ratio>{max_implausible}:{implausible}"
                )
            if (
                stmt_metrics_ratio is not None
                and float(stmt_metrics_ratio) + 1e-9 < min_stmt_metrics
            ):
                failures.append(
                    f"statements_with_metrics_ratio<{min_stmt_metrics}:{stmt_metrics_ratio}"
                )
        elif filled_core:
            failures.append("no_metric_facts_for_expected_core_metrics")

        tiny_ratio = scorecard.get("stages", {}).get("chunking", {}).get("tiny_segment_ratio")
        if tiny_ratio is not None and float(tiny_ratio) > 0.5:
            warnings.append(f"high_tiny_segment_ratio:{tiny_ratio}")

        grounded_keys = self._grounded_fact_keys(document)
        summary.update(
            {
                "metric_fact_count": fact_count,
                "source_grounding_rate": grounding_rate,
                "implausible_period_ratio": implausible,
                "statements_with_metrics_ratio": stmt_metrics_ratio,
                "core_metric_exact_match": core_match,
                "company": company,
                "year": year,
            }
        )
        return ServingGateResult(
            allow_metric_serving=not failures,
            # Segments always eligible; TOC/tiny fragments are filtered at write time.
            allow_segment_serving=True,
            failures=failures,
            warnings=warnings,
            summary=summary,
            grounded_fact_keys=grounded_keys,
        )

    def filter_metric_facts_for_serving(
        self,
        document: ParsedDocument,
        *,
        gate: ServingGateResult | None = None,
    ) -> list[FinancialMetricFact]:
        schema = document.financial_schema
        if schema is None or not schema.metric_facts:
            return []
        gate = gate or self.evaluate(document)
        if not gate.allow_metric_serving:
            return []
        allowed = set(gate.grounded_fact_keys)
        if not allowed:
            return list(schema.metric_facts)
        return [
            fact
            for fact in schema.metric_facts
            if self._fact_key(fact) in allowed
        ]

    def filter_segments_for_serving(self, segments: list[DocumentSegment]) -> list[DocumentSegment]:
        kept: list[DocumentSegment] = []
        for segment in segments:
            content = (segment.content or "").strip()
            if not content:
                continue
            compact = re.sub(r"\s+", "", content)
            if len(compact) < 12:
                continue
            if re.search(r"\.{3,}|…{2,}", content) and len(compact) < 40:
                continue
            if re.match(r"^\d{1,3}第[一二三四五六七八九十百千零〇\d]+[章节]", compact) and len(compact) < 40:
                continue
            kept.append(segment)
        return kept

    def apply_to_document(
        self,
        document: ParsedDocument,
        *,
        expectations: dict[str, Any] | None = None,
    ) -> tuple[ParsedDocument, ServingGateResult]:
        """Attach gate metadata and return a serving-safe document copy for graph/index."""
        gate = self.evaluate(document, expectations=expectations)
        serving = document.model_copy(deep=True)
        if serving.financial_schema is not None:
            serving.financial_schema.metadata["serving_gate"] = gate.to_dict()
            if not gate.allow_metric_serving:
                serving.financial_schema.metric_facts = []
                serving.financial_schema.metrics_index = {}
                for statement in serving.financial_schema.statements:
                    statement.metrics = {}
            else:
                allowed_facts = self.filter_metric_facts_for_serving(document, gate=gate)
                serving.financial_schema.metric_facts = allowed_facts
                index: dict[str, dict[str, int | float | str]] = {}
                for fact in allowed_facts:
                    index.setdefault(fact.metric_key, {})[fact.period] = fact.value
                serving.financial_schema.metrics_index = index
                for statement in serving.financial_schema.statements:
                    filtered: dict[str, dict[str, int | float | str]] = {}
                    for metric_key, periods in statement.metrics.items():
                        kept = {
                            period: value
                            for period, value in periods.items()
                            if any(
                                fact.metric_key == metric_key and fact.period == period
                                for fact in allowed_facts
                            )
                        }
                        if kept:
                            filtered[metric_key] = kept
                    statement.metrics = filtered

        if gate.allow_segment_serving:
            serving.segments = self.filter_segments_for_serving(list(document.segments))
        else:
            serving.segments = []

        # Keep gate on the artifact document too.
        if document.financial_schema is not None:
            document.financial_schema.metadata["serving_gate"] = gate.to_dict()
        return serving, gate

    @staticmethod
    def _has_filled_core_metrics(expectations: dict[str, Any]) -> bool:
        core = expectations.get("core_metrics") or {}
        for periods in core.values():
            if not isinstance(periods, dict):
                continue
            if any(value is not None for value in periods.values()):
                return True
        return False

    def _grounded_fact_keys(self, document: ParsedDocument) -> list[str]:
        schema = document.financial_schema
        if schema is None or not schema.metric_facts:
            return []
        keys: list[str] = []
        tables_by_id = {table.table_id: table for table in document.tables if table.table_id}
        corpus = self._grounding._build_corpus(document)
        for fact in schema.metric_facts:
            hit = self._grounding._ground_fact(fact, corpus=corpus, tables_by_id=tables_by_id)
            if hit.get("grounded"):
                keys.append(self._fact_key(fact))
        return keys

    def _fact_key(self, fact: FinancialMetricFact) -> str:
        return f"{fact.metric_key}::{fact.period}::{fact.value}"
