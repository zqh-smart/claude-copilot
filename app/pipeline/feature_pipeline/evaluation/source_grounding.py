"""Ground extracted metric facts against source document text/tables."""

from __future__ import annotations

import re
from typing import Any

from src.claude_copilot.schemas.document import FinancialMetricFact, ParsedDocument, ParsedTable

# Compact aliases for proximity checks (value near label is stronger evidence).
_METRIC_LABELS: dict[str, tuple[str, ...]] = {
    "revenue": ("营业收入", "营业总收入", "revenue"),
    "net_profit": ("净利润", "归属于母公司所有者的净利润", "net profit", "net income"),
    "total_assets": ("资产总计", "总资产", "total assets"),
    "total_liabilities": ("负债合计", "负债总计", "total liabilities"),
    "net_cash_from_operating_activities": (
        "经营活动产生的现金流量净额",
        "经营活动现金流量净额",
        "operating cash",
    ),
}


class SourceGroundingService:
    """Check whether extracted facts can be located in the original document text."""

    def evaluate(self, document: ParsedDocument, *, sample_limit: int = 20) -> dict[str, Any]:
        schema = document.financial_schema
        facts = list(schema.metric_facts) if schema else []
        if not facts:
            return {
                "source_grounding_rate": None,
                "source_table_grounding_rate": None,
                "grounded_fact_count": 0,
                "ungrounded_fact_count": 0,
                "ungrounded_samples": [],
                "table_ungrounded_samples": [],
            }

        corpus = self._build_corpus(document)
        tables_by_id = {
            table.table_id: table for table in document.tables if table.table_id
        }

        grounded = 0
        table_checked = 0
        table_grounded = 0
        ungrounded_samples: list[dict[str, Any]] = []
        table_ungrounded_samples: list[dict[str, Any]] = []

        for fact in facts:
            hit = self._ground_fact(fact, corpus=corpus, tables_by_id=tables_by_id)
            if hit["grounded"]:
                grounded += 1
            elif len(ungrounded_samples) < sample_limit:
                ungrounded_samples.append(hit)
            if hit.get("checked_source_table"):
                table_checked += 1
                if hit.get("in_source_table"):
                    table_grounded += 1
                elif len(table_ungrounded_samples) < sample_limit:
                    table_ungrounded_samples.append(
                        {
                            **hit,
                            "reason": "value_not_found_in_bound_source_table",
                        }
                    )

        total = len(facts)
        return {
            "source_grounding_rate": round(grounded / total, 4),
            "source_table_grounding_rate": (
                round(table_grounded / table_checked, 4) if table_checked else None
            ),
            "grounded_fact_count": grounded,
            "ungrounded_fact_count": total - grounded,
            "ungrounded_samples": ungrounded_samples,
            "table_ungrounded_samples": table_ungrounded_samples,
        }

    def _build_corpus(self, document: ParsedDocument) -> str:
        parts: list[str] = [document.raw_text or ""]
        for block in document.page_blocks:
            parts.append(block.text or "")
        for table in document.tables:
            parts.append(table.raw_markdown or "")
            parts.append(table.title or "")
            parts.extend(table.headers or [])
            for row in table.rows or []:
                parts.extend(str(cell) for cell in row)
        return "\n".join(parts)

    def _ground_fact(
        self,
        fact: FinancialMetricFact,
        *,
        corpus: str,
        tables_by_id: dict[str, ParsedTable],
    ) -> dict[str, Any]:
        variants = self._value_variants(fact.value)
        if not variants:
            return {
                "metric_key": fact.metric_key,
                "period": fact.period,
                "value": fact.value,
                "source_table_id": fact.source_table_id,
                "grounded": False,
                "reason": "non_numeric_value",
            }

        in_corpus = any(self._digits_present(corpus, variant) for variant in variants)
        in_table = False
        checked_table = False
        source_table = tables_by_id.get(fact.source_table_id or "")
        if source_table is not None:
            checked_table = True
            table_text = self._table_text(source_table)
            in_table = any(self._digits_present(table_text, variant) for variant in variants)

        label_near = False
        if in_corpus or in_table:
            search_text = self._table_text(source_table) if in_table and source_table else corpus
            label_near = self._label_near_value(
                search_text,
                metric_key=fact.metric_key,
                variants=variants,
            )

        grounded = in_table or in_corpus
        return {
            "metric_key": fact.metric_key,
            "period": fact.period,
            "value": fact.value,
            "source_table_id": fact.source_table_id,
            "grounded": grounded,
            "in_corpus": in_corpus,
            "checked_source_table": checked_table,
            "in_source_table": in_table,
            "label_near_value": label_near,
            "reason": None if grounded else "value_not_found_in_source",
        }

    def _table_text(self, table: ParsedTable) -> str:
        parts = [table.raw_markdown or "", table.title or "", " ".join(table.headers or [])]
        for row in table.rows or []:
            parts.append(" ".join(str(cell) for cell in row))
        return "\n".join(parts)

    def _value_variants(self, value: Any) -> list[str]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            text = str(value).strip()
            return [text] if text else []

        if abs(number - round(number)) < 1e-9:
            whole = int(round(number))
            abs_whole = abs(whole)
            plain = str(abs_whole)
            grouped = f"{abs_whole:,}"
            variants = [plain, grouped, f"{grouped}.00", f"{plain}.00"]
            if whole < 0:
                variants.extend([f"-{plain}", f"-{grouped}"])
            return variants

        plain = f"{abs(number):.4f}".rstrip("0").rstrip(".")
        grouped = f"{abs(number):,.4f}".rstrip("0").rstrip(".")
        variants = [plain, grouped]
        if number < 0:
            variants.extend([f"-{plain}", f"-{grouped}"])
        return variants

    def _digits_present(self, text: str, variant: str) -> bool:
        if not text or not variant:
            return False
        # Fast path: literal match (handles comma-formatted numbers in markdown tables).
        if variant in text:
            return True
        digits = re.sub(r"[^\d.]", "", variant)
        if len(digits) < 3:
            return False
        normalized = re.sub(r"[,\s]", "", text)
        return digits in normalized

    def _label_near_value(self, text: str, *, metric_key: str, variants: list[str]) -> bool:
        labels = _METRIC_LABELS.get(metric_key) or ()
        if not labels:
            return False
        window = 80
        for label in labels:
            for match in re.finditer(re.escape(label), text, flags=re.IGNORECASE):
                start = max(0, match.start() - window)
                end = min(len(text), match.end() + window)
                snippet = text[start:end]
                if any(self._digits_present(snippet, variant) for variant in variants):
                    return True
        return False
