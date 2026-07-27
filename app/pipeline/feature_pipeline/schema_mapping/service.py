from __future__ import annotations

import re
from typing import Any

from src.claude_copilot.schemas.document import (
    FinancialMetricFact,
    FinancialNoteFact,
    FinancialNoteSchema,
    FinancialSchema,
    FinancialStatementSchema,
    ParsedDocument,
    ParsedSection,
    ParsedTable,
    SemanticSectionSchema,
)


class FinancialSchemaMappingService:
    _STATEMENT_TABLE_TYPES = {"income_statement", "balance_sheet", "cash_flow", "equity"}
    _NOTE_CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
        "fair_value": ("fair value", "level 1", "level 2", "level 3"),
        "loans": ("loan", "lending", "credit exposure", "financing receivable"),
        "credit_losses": ("credit loss", "allowance", "charge-off", "chargeoff"),
        "debt": ("debt", "borrowings", "senior notes", "subordinated"),
        "deposits": ("deposit", "customer accounts"),
        "equity": ("equity", "retained earnings", "common stock"),
        "income_tax": ("income tax", "deferred tax", "tax benefit"),
        "derivatives": ("derivative", "hedging", "swap", "option"),
    }
    _NOTE_ROW_TAG_PATTERNS: dict[str, tuple[str, ...]] = {
        "balance": ("balance", "carrying", "ending", "beginning"),
        "allowance": ("allowance", "reserve", "acl"),
        "chargeoff": ("charge-off", "chargeoff", "write-off", "writeoff"),
        "rate": ("rate", "yield", "weighted average"),
        "maturity": ("maturity", "due"),
        "fair_value_level": ("level 1", "level 2", "level 3"),
    }
    _NOTE_FACT_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
        "credit_losses": {
            "beginning_balance": ("beginning balance", "balance at beginning of period"),
            "ending_balance": ("ending balance", "balance at end of period"),
            "provision_for_credit_losses": ("provision for credit losses", "credit loss expense"),
            "net_charge_offs": ("net charge-offs", "net charge offs", "net write-offs", "net write offs"),
            "gross_charge_offs": ("gross charge-offs", "gross charge offs"),
            "recoveries": ("recoveries",),
            "allowance_ratio": ("allowance ratio",),
        },
        "fair_value": {
            "total_fair_value": ("total fair value",),
            "level_1": ("level 1",),
            "level_2": ("level 2",),
            "level_3": ("level 3",),
        },
        "debt": {
            "principal_amount": ("principal amount", "principal"),
            "carrying_value": ("carrying value", "carrying amount"),
            "interest_rate": ("interest rate", "weighted average interest rate"),
            "maturity": ("maturity", "due date"),
        },
        "deposits": {
            "noninterest_bearing": ("noninterest-bearing", "noninterest bearing"),
            "interest_bearing": ("interest-bearing", "interest bearing"),
            "total_deposits": ("total deposits",),
        },
        "regulatory": {
            "cet1_ratio": ("common equity tier 1", "cet1"),
            "tier_1_capital_ratio": ("tier 1 capital ratio",),
            "total_capital_ratio": ("total capital ratio",),
            "supplementary_leverage_ratio": ("supplementary leverage ratio", "slr"),
        },
    }

    def map(self, document: ParsedDocument) -> ParsedDocument:
        prepared_tables = [self._prepare_table_for_schema(table) for table in document.tables]
        document.tables = prepared_tables
        semantic_sections = self._build_semantic_sections(document.sections)
        note_facts = self._build_note_facts(prepared_tables)
        statement_schemas = self._build_statement_schemas(
            prepared_tables,
            report_year=document.metadata.year,
        )
        note_schemas = self._build_note_schemas(prepared_tables, note_facts)
        metric_facts = self._build_metric_facts(statement_schemas, prepared_tables)
        reporting_periods = self._collect_reporting_periods(prepared_tables, statement_schemas, metric_facts)
        metrics_index = self._build_metrics_index(metric_facts)

        document.financial_schema = FinancialSchema(
            company=document.metadata.company,
            year=document.metadata.year,
            reporting_periods=reporting_periods,
            statements=statement_schemas,
            notes=note_schemas,
            semantic_sections=semantic_sections,
            metric_facts=metric_facts,
            note_facts=note_facts,
            metrics_index=metrics_index,
            metadata={
                "statement_count": len(statement_schemas),
                "note_count": len(note_schemas),
                "semantic_section_count": len(semantic_sections),
                "metric_fact_count": len(metric_facts),
                "note_fact_count": len(note_facts),
            },
        )
        return document

    def _prepare_table_for_schema(self, table: ParsedTable) -> ParsedTable:
        prepared = table.model_copy(deep=True)
        if prepared.table_type != "notes_table":
            return prepared

        if not prepared.note_category:
            prepared.note_category = self._infer_note_category(prepared)

        if not prepared.semantic_rows and prepared.rows:
            dimension_headers = self._derive_note_dimension_headers(prepared)
            if dimension_headers:
                prepared.metadata["note_dimension_headers"] = dimension_headers
            prepared.semantic_rows = self._recover_note_semantic_rows(prepared, dimension_headers=dimension_headers)

        return prepared

    def _infer_note_category(self, table: ParsedTable) -> str | None:
        text_parts: list[str] = []
        for value in [table.note_title, table.title, table.raw_markdown, table.metadata.get("source_section_title")]:
            if value:
                text_parts.append(str(value))
        combined = re.sub(r"\s+", " ", " ".join(text_parts).lower()).strip()
        if not combined:
            return None
        for category, patterns in self._NOTE_CATEGORY_PATTERNS.items():
            if any(pattern in combined for pattern in patterns):
                return category
        return "general_note"

    def _derive_note_dimension_headers(self, table: ParsedTable) -> list[str]:
        existing = table.metadata.get("note_dimension_headers")
        if isinstance(existing, list) and existing:
            return [str(item) for item in existing if str(item).strip()]

        period_candidates = {str(period).strip().lower() for period in table.period_headers}
        dimension_headers: list[str] = []
        for header in table.headers[1:]:
            cleaned = str(header).strip()
            if not cleaned:
                continue
            normalized = cleaned.lower()
            if normalized in period_candidates:
                continue
            if any(period and period in normalized for period in period_candidates):
                continue
            dimension_headers.append(cleaned)
        return dimension_headers

    def _recover_note_semantic_rows(self, table: ParsedTable, *, dimension_headers: list[str]) -> list[dict[str, Any]]:
        semantic_rows: list[dict[str, Any]] = []
        for row in table.rows:
            if not row:
                continue
            label = str(row[0]).strip()
            if not label:
                continue
            dimension_cells, period_cells = self._split_note_row_for_schema(row=row, period_count=len(table.period_headers))
            semantic_rows.append(
                {
                    "label": label,
                    "label_normalized": self._slugify(label),
                    "row_type": "metric" if self._row_has_numeric_content(dimension_cells, period_cells) else "text",
                    "dimensions": self._build_dimension_map_for_schema(dimension_headers, dimension_cells),
                    "period_values": self._build_period_map_for_schema(table.period_headers, period_cells),
                    "tags": self._classify_note_row_tags_for_schema(label),
                }
            )
        return semantic_rows

    def _split_note_row_for_schema(self, *, row: list[str], period_count: int) -> tuple[list[str], list[str]]:
        cells = [str(cell) for cell in row[1:]]
        if period_count <= 0:
            return cells, []
        if len(cells) <= period_count:
            padded_period_cells = [""] * (period_count - len(cells)) + cells
            return [], padded_period_cells
        return cells[:-period_count], cells[-period_count:]

    def _row_has_numeric_content(self, dimension_cells: list[str], period_cells: list[str]) -> bool:
        for value in [*dimension_cells, *period_cells]:
            if self._parse_numeric_value(str(value)) is not None:
                return True
        return False

    def _build_dimension_map_for_schema(self, dimension_headers: list[str], dimension_cells: list[str]) -> dict[str, str]:
        if not dimension_cells:
            return {}
        if dimension_headers:
            padded_headers = dimension_headers + [f"dimension_{index}" for index in range(len(dimension_headers) + 1, len(dimension_cells) + 1)]
            return {
                header: value.strip()
                for header, value in zip(padded_headers, dimension_cells, strict=False)
                if value.strip()
            }
        return {
            f"dimension_{index}": value.strip()
            for index, value in enumerate(dimension_cells, start=1)
            if value.strip()
        }

    def _build_period_map_for_schema(self, period_headers: list[str], period_cells: list[str]) -> dict[str, int | float | str]:
        if not period_headers:
            return {}
        padded = [""] * max(0, len(period_headers) - len(period_cells)) + [str(cell) for cell in period_cells]
        mapped: dict[str, int | float | str] = {}
        for period, cell in zip(period_headers, padded, strict=False):
            cleaned = str(cell).strip()
            if not cleaned:
                continue
            mapped[str(period)] = self._parse_numeric_value(cleaned) if self._parse_numeric_value(cleaned) is not None else cleaned
        return mapped

    def _classify_note_row_tags_for_schema(self, label: str) -> list[str]:
        normalized = label.lower()
        tags: list[str] = []
        for tag, patterns in self._NOTE_ROW_TAG_PATTERNS.items():
            if any(pattern in normalized for pattern in patterns):
                tags.append(tag)
        return tags

    def _parse_numeric_value(self, value: str) -> int | float | None:
        cleaned = value.strip().replace(",", "")
        cleaned = cleaned.replace("$", "").replace("%", "")
        cleaned = cleaned.replace("(", "-").replace(")", "")
        cleaned = cleaned.replace("?", "").replace("?", "").strip()
        if not cleaned:
            return None
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
            return None
        number = float(cleaned)
        return int(number) if number.is_integer() else number

    def _is_empty_note_placeholder(self, table: ParsedTable) -> bool:
        if table.rows or table.headers or table.semantic_rows:
            return False
        raw_text = re.sub(r"\s+", " ", str(table.raw_markdown or "")).strip().lower()
        if not raw_text:
            return True
        return raw_text in {"images/ | simple_table", "simple_table", "images/"}

    def _build_semantic_sections(self, sections: list[ParsedSection]) -> list[SemanticSectionSchema]:
        semantic_sections: list[SemanticSectionSchema] = []
        for section in sections:
            if section.metadata.get("source") != "semantic_segmentation":
                continue

            semantic_sections.append(
                SemanticSectionSchema(
                    section_id=section.section_id,
                    section_type=section.section_type,
                    title=section.title,
                    page_range=self._page_range_from_section(section),
                    confidence=self._to_float(section.metadata.get("confidence")),
                    evidence_text=self._truncate_text(section.content, max_length=400),
                    provenance={
                        "source": "semantic_segmentation",
                        "anchor_block_id": section.metadata.get("anchor_block_id"),
                    },
                )
            )
        return semantic_sections

    def _build_statement_schemas(
        self,
        tables: list[ParsedTable],
        *,
        report_year: int | None = None,
    ) -> list[FinancialStatementSchema]:
        grouped_tables: dict[tuple[str, str], list[ParsedTable]] = {}
        for table in tables:
            if table.table_type not in self._STATEMENT_TABLE_TYPES:
                continue
            group_key = self._statement_group_key(table)
            grouped_tables.setdefault(group_key, []).append(table)

        statements: list[FinancialStatementSchema] = []
        for grouped in grouped_tables.values():
            # Skip empty-shell tables so they do not become metric-less statements.
            grouped = [table for table in grouped if table.normalized_metrics]
            if not grouped:
                continue
            grouped.sort(key=lambda item: (self._page_range_from_table(item) or (item.page or 0, item.page or 0))[0])
            primary = self._select_primary_statement_table(grouped)
            metrics: dict[str, dict[str, int | float | str]] = {}
            period_headers: list[str] = []
            footnotes: list[str] = []
            page_ranges = [self._page_range_from_table(table) for table in grouped if self._page_range_from_table(table)]
            merged_table_ids = [table.table_id for table in grouped if table.table_id]
            provenances = [self._table_provenance(table) for table in grouped]

            for table in grouped:
                for period in table.period_headers:
                    normalized_period = str(period)
                    if (
                        normalized_period not in period_headers
                        and self._is_plausible_statement_period(normalized_period, report_year=report_year)
                    ):
                        period_headers.append(normalized_period)
                for metric_key, values in table.normalized_metrics.items():
                    if not isinstance(values, dict):
                        continue
                    metrics.setdefault(metric_key, {})
                    for period, value in values.items():
                        period_key = str(period)
                        if not self._is_plausible_statement_period(period_key, report_year=report_year):
                            continue
                        metrics[metric_key][period_key] = value
                for footnote in table.footnotes:
                    if footnote and footnote not in footnotes:
                        footnotes.append(footnote)

            # Drop metrics that became empty after value filters.
            metrics = {key: values for key, values in metrics.items() if values}
            if not metrics:
                continue

            period_headers = self._consolidate_period_headers(period_headers, report_year=report_year)
            statements.append(
                FinancialStatementSchema(
                    table_id=primary.table_id,
                    statement_type=primary.table_type,
                    title=self._resolve_statement_title(primary, statement_type=primary.table_type),
                    period_headers=period_headers,
                    unit=primary.unit,
                    currency=primary.currency,
                    source_section=primary.source_section,
                    page_range=self._merge_page_ranges(page_ranges),
                    metrics=metrics,
                    footnotes=footnotes,
                    provenance=self._merge_provenance(
                        provenances,
                        extra={"merged_statement_table_ids": merged_table_ids},
                    ),
                )
            )
        return statements

    def _select_primary_statement_table(self, grouped: list[ParsedTable]) -> ParsedTable:
        def score(table: ParsedTable) -> tuple[int, int, int]:
            title = (table.title or str(table.metadata.get("source_section_title") or "")).strip()
            good_title = 1 if self._title_matches_statement_type(title, table.table_type or "") else 0
            bad_title = 1 if re.search(r"(治理层|责任|内部控制|管理层讨论|公司简介)", title) else 0
            metric_n = len(table.normalized_metrics or {})
            return (good_title, -bad_title, metric_n)

        return max(grouped, key=score)

    def _resolve_statement_title(self, table: ParsedTable, *, statement_type: str) -> str:
        candidates = [
            table.title or "",
            str(table.metadata.get("source_section_title") or ""),
            str(table.metadata.get("nearby_context") or ""),
        ]
        for candidate in candidates:
            cleaned = re.split(r"[\n\r]", candidate.strip())[0].strip()
            if cleaned and self._title_matches_statement_type(cleaned, statement_type):
                return cleaned[:120]
        defaults = {
            "income_statement": "利润表",
            "balance_sheet": "资产负债表",
            "cash_flow": "现金流量表",
            "equity": "所有者权益变动表",
        }
        current = (table.title or "").strip()
        if current and self._title_matches_statement_type(current, statement_type):
            return current[:120]
        return defaults.get(statement_type, current or statement_type)

    def _title_matches_statement_type(self, title: str, statement_type: str) -> bool:
        normalized = title.lower()
        patterns = {
            "income_statement": r"(利润表|income statement|statements? of income|净收入)",
            "balance_sheet": r"(资产负债表|balance sheet)",
            "cash_flow": r"(现金流量表|cash flow)",
            "equity": r"(股东权益|所有者权益|changes in stockholders|changes in equity)",
        }
        pattern = patterns.get(statement_type)
        return bool(pattern and re.search(pattern, normalized, flags=re.IGNORECASE))

    def _is_plausible_statement_period(self, period: str, *, report_year: int | None) -> bool:
        if period in {"current_period", "prior_period"}:
            return True
        year_match = re.fullmatch(r"(19|20)\d{2}", period)
        if not year_match:
            # Keep English month-day-year headers as-is when present.
            return bool(re.search(r"(19|20)\d{2}", period))
        year = int(period)
        if not (2000 <= year <= 2035):
            return False
        if report_year is not None and (year < report_year - 5 or year > report_year + 1):
            return False
        return True

    def _consolidate_period_headers(
        self,
        periods: list[str],
        *,
        report_year: int | None,
    ) -> list[str]:
        years = [period for period in periods if re.fullmatch(r"(19|20)\d{2}", period)]
        relatives = [period for period in periods if period in {"current_period", "prior_period"}]
        others = [period for period in periods if period not in years and period not in relatives]
        if years:
            # Prefer concrete years; drop relative placeholders that usually duplicate them.
            # Preserve first-seen order so merged statement headers stay stable.
            if report_year is not None and len(years) > 4:
                keep = {
                    period
                    for period, _distance in sorted(
                        ((period, abs(int(period) - report_year)) for period in years),
                        key=lambda item: item[1],
                    )[:4]
                }
                years = [period for period in years if period in keep]
            return years + others
        return relatives + others

    def _build_note_schemas(
        self,
        tables: list[ParsedTable],
        note_facts: list[FinancialNoteFact],
    ) -> list[FinancialNoteSchema]:
        notes: list[FinancialNoteSchema] = []
        for table in tables:
            if table.table_type != "notes_table":
                continue
            if self._is_empty_note_placeholder(table):
                continue
            if not table.semantic_rows and not table.rows:
                continue
            if not table.semantic_rows and not table.note_number and not table.note_title:
                continue

            table_note_facts = [fact for fact in note_facts if fact.source_table_id == table.table_id]

            notes.append(
                FinancialNoteSchema(
                    table_id=table.table_id,
                    note_number=table.note_number,
                    note_title=table.note_title or table.title,
                    note_category=table.note_category,
                    period_headers=list(table.period_headers),
                    dimension_headers=list(table.metadata.get("note_dimension_headers") or []),
                    semantic_rows=[dict(row) for row in table.semantic_rows],
                    note_facts=table_note_facts,
                    footnotes=list(table.footnotes),
                    source_section=table.source_section,
                    page_range=self._page_range_from_table(table),
                    provenance=self._table_provenance(table),
                )
            )
        return notes

    def _build_note_facts(self, tables: list[ParsedTable]) -> list[FinancialNoteFact]:
        note_facts: list[FinancialNoteFact] = []
        for table in tables:
            if table.table_type != "notes_table":
                continue
            if not table.semantic_rows:
                continue

            page_range = self._page_range_from_table(table)
            for index, semantic_row in enumerate(table.semantic_rows, start=1):
                if not isinstance(semantic_row, dict):
                    continue
                note_facts.append(
                    FinancialNoteFact(
                        fact_key=self._resolve_note_fact_key(table=table, semantic_row=semantic_row, index=index),
                        note_number=table.note_number,
                        note_title=table.note_title or table.title,
                        note_category=table.note_category,
                        row_label=str(semantic_row.get("label") or ""),
                        row_type=str(semantic_row.get("row_type") or "") or None,
                        dimensions=self._normalize_dimension_map(semantic_row.get("dimensions")),
                        period_values=self._normalize_period_value_map(semantic_row.get("period_values")),
                        tags=self._normalize_tags(semantic_row.get("tags")),
                        source_table_id=table.table_id,
                        source_section=table.source_section,
                        page_range=page_range,
                        provenance=self._table_provenance(table),
                    )
                )
        return note_facts

    def _build_metric_facts(
        self,
        statements: list[FinancialStatementSchema],
        tables: list[ParsedTable],
    ) -> list[FinancialMetricFact]:
        tables_by_id = {table.table_id: table for table in tables if table.table_id}
        metric_facts: list[FinancialMetricFact] = []
        for statement in statements:
            if not statement.metrics:
                continue
            merged_ids = statement.provenance.get("merged_statement_table_ids") or [statement.table_id]
            if not isinstance(merged_ids, list):
                merged_ids = [statement.table_id]
            for metric_key, period_map in statement.metrics.items():
                for period, value in period_map.items():
                    source_table = self._resolve_metric_source_table(
                        metric_key=metric_key,
                        period=str(period),
                        value=value,
                        merged_ids=[str(item) for item in merged_ids if item],
                        tables_by_id=tables_by_id,
                        fallback_table_id=statement.table_id,
                    )
                    metric_facts.append(
                        FinancialMetricFact(
                            metric_key=metric_key,
                            period=str(period),
                            value=value,
                            statement_type=statement.statement_type,
                            unit=statement.unit,
                            currency=statement.currency,
                            source_table_id=source_table.table_id if source_table else statement.table_id,
                            source_table_title=(
                                source_table.title
                                if source_table and source_table.title
                                else statement.title
                            ),
                            source_section=statement.source_section,
                            page_range=(
                                self._page_range_from_table(source_table)
                                if source_table
                                else statement.page_range
                            ),
                            provenance=dict(statement.provenance),
                        )
                    )
        return metric_facts

    def _resolve_metric_source_table(
        self,
        *,
        metric_key: str,
        period: str,
        value: int | float | str,
        merged_ids: list[str],
        tables_by_id: dict[str, ParsedTable],
        fallback_table_id: str | None,
    ) -> ParsedTable | None:
        candidates = [tables_by_id[table_id] for table_id in merged_ids if table_id in tables_by_id]
        if fallback_table_id and fallback_table_id in tables_by_id:
            fallback = tables_by_id[fallback_table_id]
            if fallback not in candidates:
                candidates.append(fallback)

        for table in candidates:
            metrics = table.normalized_metrics.get(metric_key)
            if isinstance(metrics, dict) and period in metrics and self._values_equal(metrics[period], value):
                return table

        for table in candidates:
            if self._table_contains_value(table, value):
                return table

        if fallback_table_id and fallback_table_id in tables_by_id:
            return tables_by_id[fallback_table_id]
        return candidates[0] if candidates else None

    def _table_contains_value(self, table: ParsedTable, value: int | float | str) -> bool:
        variants = self._numeric_variants(value)
        if not variants:
            return False
        parts = [table.raw_markdown or "", " ".join(table.headers or [])]
        for row in table.rows or []:
            parts.append(" ".join(str(cell) for cell in row))
        text = "\n".join(parts)
        normalized = re.sub(r"[,\s]", "", text)
        return any(variant in text or variant in normalized for variant in variants)

    def _numeric_variants(self, value: int | float | str) -> list[str]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            text = str(value).strip()
            return [text] if text else []
        if abs(number - round(number)) < 1e-9:
            whole = abs(int(round(number)))
            return [str(whole), f"{whole:,}", f"{whole:,}.00", f"{whole}.00"]
        plain = f"{abs(number):.4f}".rstrip("0").rstrip(".")
        return [plain, f"{abs(number):,.4f}".rstrip("0").rstrip(".")]

    def _values_equal(self, left: Any, right: Any) -> bool:
        try:
            return abs(float(left) - float(right)) <= max(1.0, abs(float(right)) * 0.001)
        except (TypeError, ValueError):
            return str(left).strip() == str(right).strip()

    def _collect_reporting_periods(
        self,
        tables: list[ParsedTable],
        statements: list[FinancialStatementSchema],
        metric_facts: list[FinancialMetricFact],
    ) -> list[str]:
        ordered_periods: list[str] = []
        for statement in statements:
            for period in statement.period_headers:
                normalized = str(period)
                if normalized not in ordered_periods:
                    ordered_periods.append(normalized)
        for table in tables:
            for period in table.period_headers:
                normalized = str(period)
                if normalized not in ordered_periods:
                    ordered_periods.append(normalized)
        for fact in metric_facts:
            if fact.period not in ordered_periods:
                ordered_periods.append(fact.period)
        return ordered_periods

    def _build_metrics_index(
        self,
        metric_facts: list[FinancialMetricFact],
    ) -> dict[str, dict[str, int | float | str]]:
        metrics_index: dict[str, dict[str, int | float | str]] = {}
        for fact in metric_facts:
            metrics_index.setdefault(fact.metric_key, {})
            metrics_index[fact.metric_key][fact.period] = fact.value
        return metrics_index

    def _page_range_from_table(self, table: ParsedTable) -> tuple[int, int] | None:
        page_range = table.metadata.get("page_range")
        if isinstance(page_range, list) and len(page_range) == 2:
            start, end = page_range
            if isinstance(start, int) and isinstance(end, int):
                return (start, end)
        if table.page is not None:
            return (table.page, table.page)
        return None

    def _page_range_from_section(self, section: ParsedSection) -> tuple[int, int] | None:
        if section.page_start is not None and section.page_end is not None:
            return (section.page_start, section.page_end)
        if section.page_start is not None:
            return (section.page_start, section.page_start)
        return None

    def _statement_group_key(self, table: ParsedTable) -> tuple[str, str]:
        return (
            table.table_type or "statement",
            self._normalize_statement_title(table),
        )

    def _normalize_statement_title(self, table: ParsedTable) -> str:
        title = table.title or str(table.metadata.get("source_section_title") or "")
        if not title:
            return table.table_type or "statement"
        normalized = re.sub(r"\s+", " ", title.lower()).strip()
        return normalized

    def _merge_page_ranges(self, page_ranges: list[tuple[int, int]]) -> tuple[int, int] | None:
        if not page_ranges:
            return None
        start = min(page_range[0] for page_range in page_ranges)
        end = max(page_range[1] for page_range in page_ranges)
        return (start, end)

    def _merge_provenance(self, provenances: list[dict[str, Any]], *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for provenance in provenances:
            for key, value in provenance.items():
                if key not in merged:
                    merged[key] = value
                    continue
                if isinstance(value, list):
                    existing = merged.get(key) if isinstance(merged.get(key), list) else [merged.get(key)]
                    for item in value:
                        if item not in existing:
                            existing.append(item)
                    merged[key] = existing
        if extra:
            merged.update(extra)
        return merged

    def _table_provenance(self, table: ParsedTable) -> dict[str, Any]:
        provenance = {
            "table_id": table.table_id,
            "source_block_id": table.source_block_id,
            "source_section": table.source_section,
            "source_section_id": table.metadata.get("source_section_id"),
            "caption_block_id": table.metadata.get("caption_block_id"),
            "footnote_block_ids": list(table.metadata.get("footnote_block_ids") or []),
            "merged_from_table_ids": list(table.metadata.get("merged_from_table_ids") or []),
            "parse_mode": table.metadata.get("parse_mode"),
        }
        return {key: value for key, value in provenance.items() if value not in (None, [], "")}

    def _resolve_note_fact_key(
        self,
        *,
        table: ParsedTable,
        semantic_row: dict[str, Any],
        index: int,
    ) -> str:
        label = str(semantic_row.get("label_normalized") or semantic_row.get("label") or "").strip().lower()
        tags = self._normalize_tags(semantic_row.get("tags"))
        note_category = table.note_category or "general_note"

        category_patterns = self._NOTE_FACT_PATTERNS.get(note_category, {})
        for fact_key, patterns in category_patterns.items():
            if any(pattern in label for pattern in patterns):
                return fact_key

        if "chargeoff" in tags:
            return "net_charge_offs"
        if "allowance" in tags:
            return "allowance"
        if "balance" in tags:
            return "balance"
        if "rate" in tags:
            return "rate"
        if "maturity" in tags:
            return "maturity"
        if "fair_value_level" in tags:
            return self._resolve_fair_value_level_key(label)

        slug = self._slugify(label)
        return slug or f"note_fact_{index}"

    def _resolve_fair_value_level_key(self, label: str) -> str:
        if "level 1" in label:
            return "level_1"
        if "level 2" in label:
            return "level_2"
        if "level 3" in label:
            return "level_3"
        return "fair_value_level"

    def _normalize_dimension_map(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, str] = {}
        for key, item in value.items():
            if item in (None, ""):
                continue
            normalized[str(key)] = str(item)
        return normalized

    def _normalize_period_value_map(self, value: Any) -> dict[str, int | float | str]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, int | float | str] = {}
        for key, item in value.items():
            if item in (None, ""):
                continue
            normalized[str(key)] = item
        return normalized

    def _normalize_tags(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        normalized = re.sub(r"_+", "_", normalized)
        return normalized

    def _truncate_text(self, text: str, *, max_length: int) -> str:
        normalized = text.strip()
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 3].rstrip() + "..."

    def _to_float(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None
