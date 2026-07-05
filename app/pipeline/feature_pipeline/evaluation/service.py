from __future__ import annotations

from typing import Any

from src.claude_copilot.schemas.document import ParsedDocument


class ParseEvaluationBenchmarkService:
    def evaluate(
        self,
        document: ParsedDocument,
        *,
        expected: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema = document.financial_schema
        statement_types = sorted({table.table_type for table in document.tables if table.table_type})
        semantic_section_types = sorted({section.section_type for section in document.sections if section.section_type})

        report = {
            "document": {
                "doc_id": document.doc_id,
                "filename": document.metadata.filename,
                "parse_route": document.metadata.parse_route,
                "parse_backend": document.metadata.parse_backend,
                "page_count": document.metadata.page_count,
                "parsed_page_range": document.metadata.parsed_page_range,
                "parsed_page_count": document.metadata.parsed_page_count,
            },
            "counts": {
                "sections": len(document.sections),
                "semantic_sections": len(schema.semantic_sections) if schema else 0,
                "tables": len(document.tables),
                "statements": len(schema.statements) if schema else 0,
                "notes": len(schema.notes) if schema else 0,
                "metric_facts": len(schema.metric_facts) if schema else 0,
                "note_facts": len(schema.note_facts) if schema else 0,
            },
            "coverage": {
                "statement_types": statement_types,
                "semantic_section_types": semantic_section_types,
                "provenance": self._compute_provenance_coverage(document),
            "statement_metrics": self._compute_statement_metric_coverage(document),
            "statement_dimensions": self._compute_statement_dimension_coverage(document),
            "notes": self._compute_note_coverage(document),
            },
            "quality": document.quality.model_dump() if document.quality else None,
            "inventory": self._build_inventory(document),
            "checks": [],
            "failures": [],
        }

        if expected:
            self._apply_expected_checks(report, expected=expected)

        return report

    def _build_inventory(self, document: ParsedDocument) -> dict[str, Any]:
        schema = document.financial_schema
        if schema is None:
            return {"statements": [], "note_numbers": []}
        return {
            "statements": [
                {
                    "statement_type": item.statement_type,
                    "title": item.title,
                    "page_range": item.page_range,
                    "period_headers": item.period_headers,
                    "unit": item.unit,
                    "currency": item.currency,
                    "metric_keys": sorted(item.metrics),
                }
                for item in schema.statements
            ],
            "note_numbers": sorted(
                {item.note_number for item in schema.notes if item.note_number}
            ),
        }

    def _compute_provenance_coverage(self, document: ParsedDocument) -> dict[str, Any]:
        schema = document.financial_schema
        statements = schema.statements if schema else []
        notes = schema.notes if schema else []
        metric_facts = schema.metric_facts if schema else []
        note_facts = schema.note_facts if schema else []

        return {
            "statement_page_range_ratio": self._completion_ratio(statements, lambda item: item.page_range is not None),
            "statement_source_section_ratio": self._completion_ratio(statements, lambda item: bool(item.source_section)),
            "note_page_range_ratio": self._completion_ratio(notes, lambda item: item.page_range is not None),
            "note_source_section_ratio": self._completion_ratio(notes, lambda item: bool(item.source_section)),
            "metric_fact_page_range_ratio": self._completion_ratio(metric_facts, lambda item: item.page_range is not None),
            "metric_fact_source_table_ratio": self._completion_ratio(
                metric_facts,
                lambda item: bool(item.source_table_id),
            ),
            "note_fact_page_range_ratio": self._completion_ratio(note_facts, lambda item: item.page_range is not None),
            "note_fact_source_table_ratio": self._completion_ratio(
                note_facts,
                lambda item: bool(item.source_table_id),
            ),
        }

    def _compute_statement_metric_coverage(self, document: ParsedDocument) -> dict[str, Any]:
        schema = document.financial_schema
        if not schema or not schema.statements:
            return {"statement_metric_count": 0, "statements_with_metrics_ratio": 0.0}

        statements_with_metrics = sum(1 for statement in schema.statements if statement.metrics)
        statement_metric_count = sum(len(statement.metrics) for statement in schema.statements)
        return {
            "statement_metric_count": statement_metric_count,
            "statements_with_metrics_ratio": round(statements_with_metrics / len(schema.statements), 3),
        }

    def _compute_note_coverage(self, document: ParsedDocument) -> dict[str, Any]:
        schema = document.financial_schema
        if not schema or not schema.notes:
            return {
                "notes_with_number_ratio": 0.0,
                "notes_with_category_ratio": 0.0,
                "notes_with_semantic_rows_ratio": 0.0,
                "notes_with_domain_facts_ratio": 0.0,
            }

        notes = schema.notes
        return {
            "notes_with_number_ratio": self._completion_ratio(notes, lambda item: bool(item.note_number)),
            "notes_with_category_ratio": self._completion_ratio(notes, lambda item: bool(item.note_category)),
            "notes_with_semantic_rows_ratio": self._completion_ratio(notes, lambda item: bool(item.semantic_rows)),
            "notes_with_domain_facts_ratio": self._completion_ratio(notes, lambda item: bool(item.note_facts)),
        }

    def _compute_statement_dimension_coverage(self, document: ParsedDocument) -> dict[str, Any]:
        schema = document.financial_schema
        statements = schema.statements if schema else []
        return {
            "statements_with_periods_ratio": self._completion_ratio(
                statements, lambda item: bool(item.period_headers)
            ),
            "statements_with_unit_ratio": self._completion_ratio(
                statements, lambda item: bool(item.unit)
            ),
            "statements_with_currency_ratio": self._completion_ratio(
                statements, lambda item: bool(item.currency)
            ),
        }

    def _apply_expected_checks(self, report: dict[str, Any], *, expected: dict[str, Any]) -> None:
        doc = report["document"]
        counts = report["counts"]
        coverage = report["coverage"]
        failures: list[str] = report["failures"]
        checks: list[dict[str, Any]] = report["checks"]

        self._check_equals(checks, failures, "parse_route", doc["parse_route"], expected.get("parse_route"))
        self._check_equals(checks, failures, "parse_backend", doc["parse_backend"], expected.get("parse_backend"))
        self._check_equals(checks, failures, "page_count", doc["page_count"], expected.get("page_count"))
        self._check_equals(
            checks,
            failures,
            "parsed_page_count",
            doc["parsed_page_count"],
            expected.get("parsed_page_count"),
        )
        self._check_min(checks, failures, "table_count", counts["tables"], expected.get("min_tables"))
        self._check_min(checks, failures, "statement_count", counts["statements"], expected.get("min_statements"))
        self._check_min(checks, failures, "note_count", counts["notes"], expected.get("min_notes"))
        self._check_min(checks, failures, "metric_fact_count", counts["metric_facts"], expected.get("min_metric_facts"))
        self._check_min(checks, failures, "note_fact_count", counts["note_facts"], expected.get("min_note_facts"))
        self._check_subset(
            checks,
            failures,
            "statement_types",
            set(coverage["statement_types"]),
            set(expected.get("required_statement_types") or []),
        )
        self._check_subset(
            checks,
            failures,
            "semantic_section_types",
            set(coverage["semantic_section_types"]),
            set(expected.get("required_semantic_section_types") or []),
        )
        self._check_min(
            checks,
            failures,
            "statement_page_range_ratio",
            coverage["provenance"]["statement_page_range_ratio"],
            expected.get("min_statement_page_range_ratio"),
        )
        self._check_min(
            checks,
            failures,
            "note_domain_facts_ratio",
            coverage["notes"]["notes_with_domain_facts_ratio"],
            expected.get("min_note_domain_facts_ratio"),
        )
        self._check_min(
            checks,
            failures,
            "statements_with_periods_ratio",
            coverage["statement_dimensions"]["statements_with_periods_ratio"],
            expected.get("min_statement_periods_ratio"),
        )
        self._check_min(
            checks,
            failures,
            "statements_with_unit_ratio",
            coverage["statement_dimensions"]["statements_with_unit_ratio"],
            expected.get("min_statement_unit_ratio"),
        )
        self._check_min(
            checks,
            failures,
            "statements_with_currency_ratio",
            coverage["statement_dimensions"]["statements_with_currency_ratio"],
            expected.get("min_statement_currency_ratio"),
        )

    def _check_equals(
        self,
        checks: list[dict[str, Any]],
        failures: list[str],
        name: str,
        actual: Any,
        expected: Any,
    ) -> None:
        if expected is None:
            return
        passed = actual == expected
        checks.append({"name": name, "passed": passed, "actual": actual, "expected": expected})
        if not passed:
            failures.append(f"{name}: expected {expected}, got {actual}")

    def _check_min(
        self,
        checks: list[dict[str, Any]],
        failures: list[str],
        name: str,
        actual: int | float,
        expected: int | float | None,
    ) -> None:
        if expected is None:
            return
        passed = actual >= expected
        checks.append({"name": name, "passed": passed, "actual": actual, "expected_min": expected})
        if not passed:
            failures.append(f"{name}: expected >= {expected}, got {actual}")

    def _check_subset(
        self,
        checks: list[dict[str, Any]],
        failures: list[str],
        name: str,
        actual: set[str],
        expected: set[str],
    ) -> None:
        if not expected:
            return
        missing = sorted(expected - actual)
        passed = not missing
        checks.append({"name": name, "passed": passed, "actual": sorted(actual), "expected_subset": sorted(expected)})
        if not passed:
            failures.append(f"{name}: missing {missing}")

    def _completion_ratio(self, items: list[Any], predicate) -> float:
        if not items:
            return 0.0
        completed = sum(1 for item in items if predicate(item))
        return round(completed / len(items), 3)
