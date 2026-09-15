from __future__ import annotations

import re
from collections import Counter
from typing import Any

from src.claude_copilot.schemas.document import ParsedDocument, ParsedTable


class DocumentAIGoldenEvaluator:
    """Evaluate stable, human-reviewed Document AI invariants."""

    def evaluate(self, document: ParsedDocument, expected: dict[str, Any]) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        failures: list[str] = []
        table_counts = Counter(table.table_type or "unknown" for table in document.tables)
        schema = document.financial_schema

        self._equals(checks, failures, "parse_route", document.metadata.parse_route, expected.get("parse_route"))
        self._equals(checks, failures, "parse_backend", document.metadata.parse_backend, expected.get("parse_backend"))
        self._equals(checks, failures, "page_count", document.metadata.page_count, expected.get("page_count"))
        self._equals(
            checks,
            failures,
            "parsed_page_count",
            document.metadata.parsed_page_count,
            expected.get("parsed_page_count"),
        )
        self._minimum(
            checks,
            failures,
            "metric_fact_count",
            len(schema.metric_facts) if schema else 0,
            expected.get("min_metric_facts"),
        )
        self._minimum(
            checks,
            failures,
            "note_fact_count",
            len(schema.note_facts) if schema else 0,
            expected.get("min_note_facts"),
        )

        for table_type, minimum in (expected.get("min_table_type_counts") or {}).items():
            self._minimum(
                checks,
                failures,
                f"table_type:{table_type}",
                table_counts[table_type],
                minimum,
            )
        for table_type, maximum in (expected.get("max_table_type_counts") or {}).items():
            self._maximum(
                checks,
                failures,
                f"table_type:{table_type}",
                table_counts[table_type],
                maximum,
            )

        for index, table_expected in enumerate(expected.get("required_tables") or [], start=1):
            name = table_expected.get("name") or f"required_table_{index}"
            matches = self._find_tables(document.tables, table_expected)
            present = bool(matches)
            checks.append({"name": name, "passed": present, "match_count": len(matches)})
            if not present:
                failures.append(f"{name}: no matching table")
                continue
            required_metrics = set(table_expected.get("required_metric_keys") or [])
            matches.sort(
                key=lambda table: len(required_metrics.intersection(table.normalized_metrics)),
                reverse=True,
            )
            self._check_table(checks, failures, name, matches[0], table_expected)

        for index, table_expected in enumerate(expected.get("forbidden_tables") or [], start=1):
            name = table_expected.get("name") or f"forbidden_table_{index}"
            matches = self._find_tables(document.tables, table_expected)
            passed = not matches
            checks.append({"name": name, "passed": passed, "match_count": len(matches)})
            if not passed:
                failures.append(f"{name}: found {len(matches)} forbidden table(s)")

        required_notes = set(expected.get("required_note_numbers") or [])
        actual_notes = {
            table.note_number
            for table in document.tables
            if table.table_type == "notes_table" and table.note_number
        }
        if required_notes:
            missing = sorted(required_notes - actual_notes)
            passed = not missing
            checks.append(
                {
                    "name": "required_note_numbers",
                    "passed": passed,
                    "actual": sorted(actual_notes),
                    "expected_subset": sorted(required_notes),
                }
            )
            if missing:
                failures.append(f"required_note_numbers: missing {missing}")

        return {
            "passed": not failures,
            "check_count": len(checks),
            "checks": checks,
            "failures": failures,
        }

    def _find_tables(self, tables: list[ParsedTable], expected: dict[str, Any]) -> list[ParsedTable]:
        title_regex = expected.get("title_regex")
        table_type = expected.get("table_type")
        return [
            table
            for table in tables
            if (not table_type or table.table_type == table_type)
            and (
                not title_regex
                or re.search(title_regex, table.title or "", flags=re.IGNORECASE) is not None
            )
        ]

    def _check_table(
        self,
        checks: list[dict[str, Any]],
        failures: list[str],
        name: str,
        table: ParsedTable,
        expected: dict[str, Any],
    ) -> None:
        for field in ("unit", "currency", "note_number"):
            self._equals(
                checks,
                failures,
                f"{name}:{field}",
                getattr(table, field),
                expected.get(field),
            )

        expected_periods = expected.get("periods")
        if expected_periods is not None:
            self._equals(
                checks,
                failures,
                f"{name}:periods",
                list(table.period_headers),
                list(expected_periods),
            )

        required_metrics = set(expected.get("required_metric_keys") or [])
        if required_metrics:
            actual_metrics = set(table.normalized_metrics)
            missing = sorted(required_metrics - actual_metrics)
            passed = not missing
            checks.append(
                {
                    "name": f"{name}:metric_keys",
                    "passed": passed,
                    "actual": sorted(actual_metrics),
                    "expected_subset": sorted(required_metrics),
                }
            )
            if missing:
                failures.append(f"{name}:metric_keys missing {missing}")

    def _equals(
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

    def _minimum(
        self,
        checks: list[dict[str, Any]],
        failures: list[str],
        name: str,
        actual: int,
        expected: int | None,
    ) -> None:
        if expected is None:
            return
        passed = actual >= expected
        checks.append({"name": name, "passed": passed, "actual": actual, "expected_min": expected})
        if not passed:
            failures.append(f"{name}: expected >= {expected}, got {actual}")

    def _maximum(
        self,
        checks: list[dict[str, Any]],
        failures: list[str],
        name: str,
        actual: int,
        expected: int | None,
    ) -> None:
        if expected is None:
            return
        passed = actual <= expected
        checks.append({"name": name, "passed": passed, "actual": actual, "expected_max": expected})
        if not passed:
            failures.append(f"{name}: expected <= {expected}, got {actual}")
