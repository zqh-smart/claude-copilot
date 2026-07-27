from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from app.pipeline.feature_pipeline.evaluation.source_grounding import SourceGroundingService
from src.claude_copilot.schemas.document import ParsedDocument

Direction = Literal["higher_better", "lower_better", "context"]


@dataclass(frozen=True)
class MetricSpec:
    name: str
    direction: Direction
    description: str


STAGE_METRIC_SPECS: dict[str, list[MetricSpec]] = {
    "parse": [
        MetricSpec("text_coverage", "higher_better", "Share of pages with extractable text"),
        MetricSpec("parse_confidence", "higher_better", "Parser quality confidence"),
        MetricSpec("heading_ratio", "lower_better", "Heading blocks / all blocks (noise proxy)"),
        MetricSpec("table_count", "context", "Detected tables (interpret with accuracy)"),
        MetricSpec("pages_per_second", "higher_better", "Parse throughput"),
    ],
    "cleaning": [
        MetricSpec("blocks_removed_ratio", "context", "Fraction of blocks removed by cleaning"),
        MetricSpec("header_footer_remaining", "lower_better", "Remaining header/footer blocks"),
        MetricSpec("toc_like_remaining", "lower_better", "Remaining TOC-like lines"),
        MetricSpec("duplicate_block_ratio", "lower_better", "Near-duplicate blocks after cleaning"),
    ],
    "segmentation": [
        MetricSpec("semantic_section_count", "context", "Detected semantic sections"),
        MetricSpec("required_section_types_hit", "higher_better", "Fraction of required section types found"),
        MetricSpec("false_anchor_rate_proxy", "lower_better", "Non-title-like semantic anchors"),
    ],
    "schema": [
        MetricSpec("statements_with_periods_ratio", "higher_better", "Statements that have period headers"),
        MetricSpec("statements_with_metrics_ratio", "higher_better", "Statements that have metrics"),
        MetricSpec("core_metric_exact_match", "higher_better", "Exact match rate on golden core metrics"),
        MetricSpec("source_grounding_rate", "higher_better", "Facts whose values appear in source text/tables"),
        MetricSpec("source_table_grounding_rate", "higher_better", "Facts whose values appear in bound source table"),
        MetricSpec("implausible_period_ratio", "lower_better", "Dirty/implausible period tokens"),
        MetricSpec("provenance_metric_ratio", "higher_better", "Metric facts with source table id"),
    ],
    "chunking": [
        MetricSpec("segment_count", "context", "Total segments"),
        MetricSpec("semantic_section_share", "higher_better", "Share of section-aware segments"),
        MetricSpec("avg_segment_chars", "context", "Average segment length"),
        MetricSpec("tiny_segment_ratio", "lower_better", "Segments shorter than 40 chars"),
    ],
}


class StageScorecardService:
    """Compute per-stage metrics for positive/negative optimization tracking."""

    _TOC_LIKE_RE = re.compile(r"(\.{3,}|…{2,}|第[一二三四五六七八九十百千零〇\d]+[章节].*\d+\s*$)")

    def build_from_document(
        self,
        document: ParsedDocument,
        *,
        expectations: dict[str, Any] | None = None,
        timings: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Scorecard from a fully processed document (used by serving gate)."""
        return self.build(
            parsed=document,
            cleaned=document,
            segmented=document,
            schemed=document,
            segments=list(document.segments),
            timings=timings or {},
            expectations=expectations,
        )

    def build(
        self,
        *,
        parsed: ParsedDocument,
        cleaned: ParsedDocument,
        segmented: ParsedDocument,
        schemed: ParsedDocument,
        segments: list[Any],
        timings: dict[str, float],
        expectations: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        expectations = expectations or {}
        stages = {
            "parse": self._parse_metrics(parsed, timings.get("parse", 0.0)),
            "cleaning": self._cleaning_metrics(parsed, cleaned),
            "segmentation": self._segmentation_metrics(segmented, expectations),
            "schema": self._schema_metrics(schemed, expectations),
            "chunking": self._chunking_metrics(segments),
        }
        return {
            "document": {
                "doc_id": schemed.doc_id,
                "filename": schemed.metadata.filename,
                "parse_route": schemed.metadata.parse_route,
                "page_count": schemed.metadata.page_count,
            },
            "timings": timings,
            "stages": stages,
            "metric_specs": {
                stage: [spec.__dict__ for spec in specs]
                for stage, specs in STAGE_METRIC_SPECS.items()
            },
            "summary_scores": self._summary_scores(stages),
        }

    def compare(self, *, current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
        diffs: list[dict[str, Any]] = []
        regressions: list[str] = []
        improvements: list[str] = []

        for stage, specs in STAGE_METRIC_SPECS.items():
            current_metrics = current.get("stages", {}).get(stage, {})
            baseline_metrics = baseline.get("stages", {}).get(stage, {})
            for spec in specs:
                if spec.direction == "context":
                    continue
                cur = current_metrics.get(spec.name)
                base = baseline_metrics.get(spec.name)
                if cur is None or base is None:
                    continue
                delta = round(float(cur) - float(base), 6)
                if abs(delta) < 1e-9:
                    direction = "="
                elif spec.direction == "higher_better":
                    direction = "+" if delta > 0 else "-"
                else:
                    direction = "+" if delta < 0 else "-"
                item = {
                    "stage": stage,
                    "metric": spec.name,
                    "baseline": base,
                    "current": cur,
                    "delta": delta,
                    "verdict": direction,
                }
                diffs.append(item)
                label = f"{stage}.{spec.name}: {base} -> {cur} ({delta:+})"
                if direction == "+":
                    improvements.append(label)
                elif direction == "-":
                    regressions.append(label)

        return {
            "improvements": improvements,
            "regressions": regressions,
            "diffs": diffs,
            "net_verdict": self._net_verdict(improvements, regressions, current, baseline),
        }

    def _parse_metrics(self, document: ParsedDocument, parse_seconds: float) -> dict[str, Any]:
        blocks = document.page_blocks
        heading_n = sum(1 for block in blocks if block.block_type == "heading")
        page_count = document.metadata.page_count or 0
        return {
            "text_coverage": document.quality.text_coverage if document.quality else 0.0,
            "parse_confidence": document.quality.confidence if document.quality else 0.0,
            "heading_ratio": round(heading_n / max(len(blocks), 1), 4),
            "table_count": len(document.tables),
            "pages_per_second": round(page_count / parse_seconds, 3) if parse_seconds > 0 else 0.0,
            "block_count": len(blocks),
        }

    def _cleaning_metrics(self, before: ParsedDocument, after: ParsedDocument) -> dict[str, Any]:
        before_n = len(before.page_blocks)
        after_n = len(after.page_blocks)
        removed_ratio = round((before_n - after_n) / max(before_n, 1), 4)
        header_footer = sum(1 for block in after.page_blocks if block.block_type in {"header", "footer"})
        toc_like = sum(1 for block in after.page_blocks if self._TOC_LIKE_RE.search(block.text or ""))
        norms = [re.sub(r"\s+", "", (block.text or "").lower()) for block in after.page_blocks]
        counts = Counter(norm for norm in norms if norm)
        dupes = sum(count - 1 for count in counts.values() if count > 1)
        return {
            "blocks_removed_ratio": removed_ratio,
            "header_footer_remaining": header_footer,
            "toc_like_remaining": toc_like,
            "duplicate_block_ratio": round(dupes / max(after_n, 1), 4),
            "blocks_before": before_n,
            "blocks_after": after_n,
        }

    def _segmentation_metrics(
        self,
        document: ParsedDocument,
        expectations: dict[str, Any],
    ) -> dict[str, Any]:
        semantic = [
            section
            for section in document.sections
            if section.metadata.get("source") == "semantic_segmentation"
        ]
        types = {section.section_type for section in semantic if section.section_type}
        required = set(expectations.get("required_semantic_section_types") or [])
        hit = len(required & types) / max(len(required), 1) if required else (1.0 if types else 0.0)
        false_anchors = 0
        for section in semantic:
            title = section.title or ""
            if len(title) > 48 or re.search(r"(详见|请见|参见)", title) or title.endswith(("。", "，")):
                false_anchors += 1
        return {
            "semantic_section_count": len(semantic),
            "required_section_types_hit": round(hit, 4),
            "false_anchor_rate_proxy": round(false_anchors / max(len(semantic), 1), 4),
            "semantic_types": sorted(types),
        }

    def _schema_metrics(
        self,
        document: ParsedDocument,
        expectations: dict[str, Any],
    ) -> dict[str, Any]:
        schema = document.financial_schema
        statements = schema.statements if schema else []
        metric_facts = schema.metric_facts if schema else []
        with_periods = sum(1 for item in statements if item.period_headers)
        with_metrics = sum(1 for item in statements if item.metrics)
        index = schema.metrics_index if schema else {}

        golden_metrics = expectations.get("core_metrics") or {}
        matched = 0
        total = 0
        details: list[dict[str, Any]] = []
        for metric_key, periods in golden_metrics.items():
            actual_periods = index.get(metric_key) or {}
            for period, expected_value in periods.items():
                total += 1
                actual_value = actual_periods.get(period)
                ok = self._values_equal(actual_value, expected_value)
                if ok:
                    matched += 1
                details.append(
                    {
                        "metric_key": metric_key,
                        "period": period,
                        "expected": expected_value,
                        "actual": actual_value,
                        "matched": ok,
                    }
                )

        all_periods: list[str] = []
        for statement in statements:
            all_periods.extend(statement.period_headers or [])
        implausible = [
            period
            for period in all_periods
            if re.fullmatch(r"(19|20)\d{2}", period) and not (2000 <= int(period) <= 2035)
        ]
        # Also treat clearly weird years outside report window if year known.
        report_year = document.metadata.year
        if report_year:
            for period in all_periods:
                if re.fullmatch(r"(19|20)\d{2}", period):
                    year = int(period)
                    if year < report_year - 5 or year > report_year + 1:
                        implausible.append(period)

        provenance = sum(1 for fact in metric_facts if fact.source_table_id)
        grounding = SourceGroundingService().evaluate(document)
        return {
            "statements_with_periods_ratio": round(with_periods / max(len(statements), 1), 4),
            "statements_with_metrics_ratio": round(with_metrics / max(len(statements), 1), 4),
            "core_metric_exact_match": round(matched / max(total, 1), 4) if total else None,
            "core_metric_details": details,
            "source_grounding_rate": grounding["source_grounding_rate"],
            "source_table_grounding_rate": grounding["source_table_grounding_rate"],
            "ungrounded_fact_count": grounding["ungrounded_fact_count"],
            "ungrounded_samples": grounding["ungrounded_samples"],
            "implausible_period_ratio": round(len(set(implausible)) / max(len(all_periods), 1), 4),
            "provenance_metric_ratio": round(provenance / max(len(metric_facts), 1), 4),
            "metric_fact_count": len(metric_facts),
            "statement_count": len(statements),
        }

    def _chunking_metrics(self, segments: list[Any]) -> dict[str, Any]:
        if not segments:
            return {
                "segment_count": 0,
                "semantic_section_share": 0.0,
                "avg_segment_chars": 0.0,
                "tiny_segment_ratio": 0.0,
            }
        semantic_n = sum(
            1
            for segment in segments
            if getattr(segment, "metadata", {}).get("content_type") == "semantic_section"
        )
        lengths = [len(segment.content or "") for segment in segments]
        tiny = sum(1 for length in lengths if length < 40)
        return {
            "segment_count": len(segments),
            "semantic_section_share": round(semantic_n / len(segments), 4),
            "avg_segment_chars": round(sum(lengths) / len(lengths), 2),
            "tiny_segment_ratio": round(tiny / len(segments), 4),
        }

    def _summary_scores(self, stages: dict[str, dict[str, Any]]) -> dict[str, float | None]:
        return {
            "parse_confidence": stages["parse"].get("parse_confidence"),
            "core_metric_exact_match": stages["schema"].get("core_metric_exact_match"),
            "source_grounding_rate": stages["schema"].get("source_grounding_rate"),
            "required_section_types_hit": stages["segmentation"].get("required_section_types_hit"),
            "tiny_segment_ratio": stages["chunking"].get("tiny_segment_ratio"),
            "implausible_period_ratio": stages["schema"].get("implausible_period_ratio"),
        }

    def _net_verdict(
        self,
        improvements: list[str],
        regressions: list[str],
        current: dict[str, Any],
        baseline: dict[str, Any],
    ) -> str:
        cur_core = current.get("summary_scores", {}).get("core_metric_exact_match")
        base_core = baseline.get("summary_scores", {}).get("core_metric_exact_match")
        if cur_core is not None and base_core is not None and cur_core < base_core:
            return "negative"
        cur_ground = current.get("summary_scores", {}).get("source_grounding_rate")
        base_ground = baseline.get("summary_scores", {}).get("source_grounding_rate")
        if (
            cur_ground is not None
            and base_ground is not None
            and float(cur_ground) + 1e-9 < float(base_ground)
        ):
            return "negative"
        if regressions and not improvements:
            return "negative"
        if improvements and not regressions:
            return "positive"
        if improvements and regressions:
            return "mixed"
        return "neutral"

    def _values_equal(self, actual: Any, expected: Any) -> bool:
        if actual is None:
            return False
        try:
            return abs(float(actual) - float(expected)) <= max(1.0, abs(float(expected)) * 0.001)
        except (TypeError, ValueError):
            return str(actual).strip() == str(expected).strip()
