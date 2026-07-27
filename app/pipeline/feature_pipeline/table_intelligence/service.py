from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from src.claude_copilot.schemas.document import ParsedDocument, ParsedSection, ParsedTable


class TableIntelligenceService:
    _TABLE_TYPE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
        (
            "income_statement",
            (
                "statements of income",
                "statement of income",
                "income statement",
                "statements of earnings",
                "statement of earnings",
                "comprehensive income",
                "statement of operations",
                "statements of operations",
                "合并利润表",
                "母公司利润表",
                "利润表",
            ),
        ),
        (
            "balance_sheet",
            (
                "balance sheets",
                "balance sheet",
                "financial position",
                "assets and liabilities",
                "合并资产负债表",
                "母公司资产负债表",
                "资产负债表",
            ),
        ),
        (
            "cash_flow",
            (
                "cash flows",
                "cash flow",
                "operating activities",
                "investing activities",
                "financing activities",
                "合并现金流量表",
                "母公司现金流量表",
                "现金流量表",
            ),
        ),
        (
            "equity",
            (
                "stockholders' equity",
                "stockholders’ equity",
                "shareholders' equity",
                "shareholders’ equity",
                "changes in equity",
                "changes in stockholders",
                "合并股东权益变动表",
                "合并所有者权益变动表",
                "股东权益变动表",
                "所有者权益变动表",
            ),
        ),
    ]

    _UNIT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
        ("billions", ("in billion", "in billions", "€b", "$b", "单位：亿元", "单位:亿元")),
        ("millions", ("in million", "in millions", "€m", "$m", "单位：万元", "单位:万元", "人民币万元")),
        ("thousands", ("in thousand", "in thousands", "€k", "$k")),
        ("yuan", ("单位：元", "单位:元", "人民币元")),
    ]

    _ANALYSIS_TABLE_PATTERNS = (
        "horizontal analysis",
        "vertical analysis",
        "ratio analysis",
        "year-on-year",
        "year over year",
        "analysis",
    )
    _PROFILE_TABLE_PATTERNS = ("company profile", "corporate profile")

    _METRIC_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
        "income_statement": {
            "revenue": (
                "revenue",
                "total net revenue",
                "total revenue",
                "net sales",
                "total net sales",
                "营业收入",
                "营业总收入",
            ),
            "interest_income": ("interest income", "total interest income", "利息收入"),
            "interest_expense": ("interest expense", "total interest expense", "利息支出"),
            "net_interest_income": ("net interest income", "利息净收入"),
            "noninterest_income": ("noninterest income",),
            "noninterest_revenue": ("noninterest revenue",),
            "cost_of_sales": ("cost of sales", "cost of products sold", "cost of revenue", "营业成本"),
            "gross_margin": ("gross margin", "gross profit", "毛利润", "毛利"),
            "operating_expenses": ("operating expenses", "total operating expenses", "营业支出"),
            "operating_income": ("operating income", "income from operations", "营业利润"),
            "provision_for_credit_losses": ("provision for credit losses",),
            "noninterest_expense": ("noninterest expense",),
            "income_before_income_tax_expense": ("income before income tax expense", "利润总额"),
            "income_tax_expense": ("income tax expense", "所得税费用"),
            "net_income": (
                "net income",
                "net income applicable to common stockholders",
                "净利润",
                "归属于母公司所有者的净利润",
            ),
            "earnings_per_share_basic": ("basic earnings per share", "basic eps", "基本每股收益"),
            "earnings_per_share_diluted": ("diluted earnings per share", "diluted eps", "稀释每股收益"),
        },
        "balance_sheet": {
            "cash_and_cash_equivalents": (
                "cash and cash equivalents",
                "cash and due from banks",
                "货币资金",
            ),
            "investment_securities": (
                "investment securities",
                "securities available-for-sale",
                "available-for-sale securities",
                "交易性金融资产",
            ),
            "loans": ("loans", "total loans", "发放贷款和垫款"),
            "goodwill": ("goodwill", "商誉"),
            "intangible_assets": ("intangible assets", "无形资产"),
            "total_assets": ("total assets", "资产总计", "资产合计"),
            "debt": ("long-term debt", "total debt", "borrowings", "长期借款", "短期借款"),
            "total_liabilities": ("total liabilities", "负债合计", "负债总计"),
            "total_deposits": ("total deposits", "吸收存款"),
            "retained_earnings": ("retained earnings", "未分配利润"),
            "accumulated_other_comprehensive_income": (
                "accumulated other comprehensive income",
                "accumulated other comprehensive loss",
                "其他综合收益",
            ),
            "total_equity": (
                "total equity",
                "total shareholders' equity",
                "total stockholders' equity",
                "total stockholders’ equity",
                "所有者权益合计",
                "股东权益合计",
            ),
            "total_stockholders_equity": (
                "total stockholders' equity",
                "total stockholders’ equity",
                "归属于母公司所有者权益合计",
            ),
            "accounts_receivable": ("accounts receivable", "应收账款"),
            "inventory": ("inventory", "inventories", "存货"),
            "current_assets": ("current assets", "流动资产合计"),
            "current_liabilities": ("current liabilities", "流动负债合计"),
        },
        "cash_flow": {
            "net_income": ("net income", "净利润"),
            "depreciation_and_amortization": ("depreciation and amortization", "depreciation", "折旧和摊销"),
            "net_cash_from_operating_activities": (
                "net cash provided by operating activities",
                "net cash from operating activities",
                "net cash provided by operating",
                "cash generated by operating activities",
                "经营活动产生的现金流量净额",
            ),
            "net_cash_from_investing_activities": (
                "net cash used in investing activities",
                "net cash from investing activities",
                "net cash used in investing",
                "投资活动产生的现金流量净额",
            ),
            "net_cash_from_financing_activities": (
                "net cash used in financing activities",
                "net cash from financing activities",
                "net cash provided by financing activities",
                "net cash provided by financing",
                "筹资活动产生的现金流量净额",
            ),
            "capital_expenditures": (
                "capital expenditures",
                "purchases of property and equipment",
                "additions to premises and equipment",
                "购建固定资产",
            ),
            "free_cash_flow": ("free cash flow",),
            "cash_and_cash_equivalents_at_end_of_period": (
                "cash and cash equivalents at end of period",
                "cash and cash equivalents at the end of the period",
                "期末现金及现金等价物余额",
            ),
            "cash_and_due_from_banks_at_end_of_period": (
                "cash and due from banks at the end of the period",
                "cash at end of period",
            ),
        },
        "equity": {
            "additional_paid_in_capital": (
                "additional paid-in capital",
                "additional paid in capital",
                "资本公积",
            ),
            "total_stockholders_equity": (
                "total stockholders' equity",
                "total stockholders’ equity",
                "归属于母公司所有者权益合计",
            ),
            "total_equity": ("total equity", "total shareholders' equity", "所有者权益合计"),
            "common_stock": ("common stock", "股本"),
            "treasury_stock": ("treasury stock", "库存股"),
            "retained_earnings": ("retained earnings", "未分配利润"),
            "accumulated_other_comprehensive_income": (
                "accumulated other comprehensive income",
                "accumulated other comprehensive loss",
                "其他综合收益",
            ),
        },
    }

    _NOTE_CATEGORY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
        ("basis_of_presentation", ("basis of presentation", "significant accounting policies", "accounting policies")),
        ("loans", ("loan", "lending", "financing receivable", "credit exposure")),
        ("credit_losses", ("credit loss", "allowance for credit losses", "acl", "charge-off", "chargeoff")),
        ("fair_value", ("fair value", "level 1", "level 2", "level 3")),
        ("derivatives", ("derivative", "hedging", "swap", "option")),
        ("investment_securities", ("investment securities", "available-for-sale", "held-to-maturity", "afs", "htm")),
        ("deposits", ("deposit", "customer accounts")),
        ("debt", ("long-term debt", "borrowings", "senior notes", "subordinated debt")),
        ("leases", ("lease", "right-of-use")),
        ("income_tax", ("income tax", "tax benefit", "deferred tax")),
        ("equity", ("stockholders' equity", "share-based compensation", "common stock", "retained earnings")),
        ("commitments_contingencies", ("commitment", "contingenc", "guarantee", "litigation")),
        ("regulatory", ("regulatory capital", "capital ratios", "basel")),
        ("revenue", ("revenue", "fee", "commission")),
        ("segments", ("segment", "line of business")),
        ("acquisitions", ("acquisition", "business combination", "goodwill", "intangibles")),
    ]

    _NOTE_ROW_TAG_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
        ("policy", ("policy", "method", "assumption")),
        ("balance", ("balance", "ending", "carrying", "amortized cost")),
        ("allowance", ("allowance", "reserve", "acl")),
        ("chargeoff", ("charge-off", "chargeoff", "write-off", "writeoff")),
        ("rate", ("rate", "yield", "weighted average")),
        ("maturity", ("maturity", "due after", "due within")),
        ("fair_value_level", ("level 1", "level 2", "level 3")),
        ("exposure", ("exposure", "notional", "commitment")),
    ]

    def enhance(self, document: ParsedDocument) -> ParsedDocument:
        if not document.tables:
            return document

        report_year = document.metadata.year
        semantic_sections = [section for section in document.sections if section.metadata.get("source") == "semantic_segmentation"]
        enhanced_tables = [
            self._annotate_table(
                table,
                semantic_sections,
                document.page_blocks,
                report_year=report_year,
            )
            for table in document.tables
        ]
        enhanced_tables = self._inherit_continuation_context(enhanced_tables)
        merged_tables = self._merge_cross_page_tables(enhanced_tables)
        document.tables = [self._apply_normalized_metrics(table) for table in merged_tables]
        return document

    def _annotate_table(
        self,
        table: ParsedTable,
        semantic_sections: list[ParsedSection],
        page_blocks: list,
        *,
        report_year: int | None = None,
    ) -> ParsedTable:
        enhanced = self._promote_embedded_header(table.model_copy(deep=True))
        source_section = self._find_source_section(table, semantic_sections, page_blocks)
        source_title = source_section.title if source_section else None
        source_type = source_section.section_type if source_section else None

        if source_type:
            enhanced.source_section = source_type
        if source_title:
            enhanced.metadata["source_section_title"] = source_title
        if source_section and source_section.section_id:
            enhanced.metadata["source_section_id"] = source_section.section_id
        nearby_context = self._nearby_block_context(table, page_blocks)
        if nearby_context:
            enhanced.metadata["nearby_context"] = nearby_context

        if not enhanced.title and source_title and source_type in {"financial_statement", "financial_note"}:
            enhanced.title = source_title

        enhanced = self._recover_statement_header_row(enhanced)
        enhanced.period_headers = self._extract_period_headers(enhanced, report_year=report_year)
        enhanced.unit = self._extract_unit(enhanced, source_section)
        enhanced.currency = self._extract_currency(enhanced, source_section)
        enhanced.table_type = self._classify_table_type(enhanced, source_section)
        if not enhanced.period_headers and enhanced.table_type in {
            "income_statement",
            "balance_sheet",
            "cash_flow",
            "equity",
        }:
            enhanced.period_headers = self._infer_statement_periods(
                enhanced,
                source_section,
                report_year=report_year,
            )
        if enhanced.table_type == "notes_table":
            enhanced.note_number, enhanced.note_title = self._extract_note_identity(enhanced)
            enhanced.note_category = self._classify_note_category(enhanced)
        enhanced.metadata["table_header_signature"] = self._header_signature(enhanced.headers)
        enhanced.metadata["page_range"] = [enhanced.page, enhanced.page]
        return enhanced

    def _find_source_section(self, table: ParsedTable, sections: list[ParsedSection], page_blocks: list) -> ParsedSection | None:
        page = table.page
        if page is None:
            return None

        block_order_lookup = {block.block_id: block.order for block in page_blocks if block.block_id}
        table_order = block_order_lookup.get(table.source_block_id)
        if table_order is not None:
            ordered_matches = [
                section
                for section in sections
                if section.page_start is not None
                and section.page_end is not None
                and section.page_start <= page <= section.page_end
                and self._anchor_order(section, block_order_lookup) is not None
                and self._anchor_order(section, block_order_lookup) <= table_order
            ]
            if ordered_matches:
                ordered_matches.sort(
                    key=lambda section: (
                        table_order - (self._anchor_order(section, block_order_lookup) or 0),
                        0 if section.section_type in {"financial_statement", "financial_note", "risk_section"} else 1,
                        -(section.metadata.get("confidence") or 0.0),
                    )
                )
                return ordered_matches[0]

        matches = [
            section
            for section in sections
            if section.page_start is not None
            and section.page_end is not None
            and section.page_start <= page <= section.page_end
        ]
        if not matches:
            return None

        matches.sort(
            key=lambda section: (
                0 if section.section_type in {"financial_statement", "financial_note", "risk_section"} else 1,
                -(section.metadata.get("confidence") or 0.0),
                (section.page_end or page) - (section.page_start or page),
            )
        )
        return matches[0]

    def _anchor_order(self, section: ParsedSection, block_order_lookup: dict[str, int | None]) -> int | None:
        anchor_block_id = section.metadata.get("anchor_block_id")
        if not anchor_block_id:
            return None
        return block_order_lookup.get(anchor_block_id)

    def _classify_table_type(self, table: ParsedTable, source_section: ParsedSection | None) -> str:
        title_text = self._normalize_text(table.title or "")
        source_title_text = self._normalize_text(table.metadata.get("source_section_title", ""))
        nearby_text = self._normalize_text(str(table.metadata.get("nearby_context") or ""))
        content_text = self._normalize_text(
            " ".join(
                [
                    title_text,
                    source_title_text,
                    nearby_text,
                    " ".join(table.headers),
                    " ".join(row[0] for row in table.rows[:12] if row),
                    table.raw_markdown or "",
                ]
            )
        )

        if any(pattern in title_text for pattern in self._PROFILE_TABLE_PATTERNS):
            return "profile_table"
        if any(pattern in title_text for pattern in self._ANALYSIS_TABLE_PATTERNS):
            return "analysis_table"
        if (
            "notes to" in title_text
            or re.match(r"^note\s+\d+", title_text)
            or "财务报表附注" in title_text
            or re.match(r"^附注\s*\d+", title_text)
        ):
            return "notes_table"
        if (
            re.match(r"^item\s+\d+", title_text)
            or title_text in {"form 10-k", "table of contents", "signatures"}
        ):
            return "other_table"

        # Row labels are the strongest signal for Chinese primary statements.
        # Inherited titles like “合并资产负债表” must not override a profit/cash table body.
        inferred = self._infer_type_from_row_labels(content_text)
        if inferred:
            return inferred

        for table_type, patterns in self._TABLE_TYPE_PATTERNS:
            if any(pattern in title_text for pattern in patterns):
                return table_type

        if source_section and source_section.section_type == "financial_note":
            return "notes_table"
        if (
            "notes to" in source_title_text
            or re.match(r"^note\s+\d+", source_title_text)
            or "财务报表附注" in source_title_text
        ):
            return "notes_table"

        for table_type, patterns in self._TABLE_TYPE_PATTERNS:
            if any(pattern in source_title_text for pattern in patterns):
                return table_type
            if any(pattern in nearby_text for pattern in patterns):
                return table_type

        if table.metadata.get("raw_table_type") == "complex_table":
            return "notes_table"

        raw_markdown_text = self._normalize_text(table.raw_markdown or "")
        for table_type, patterns in self._TABLE_TYPE_PATTERNS:
            if any(pattern in raw_markdown_text for pattern in patterns):
                return table_type

        return "notes_table"

    def _infer_type_from_row_labels(self, content_text: str) -> str | None:
        balance_cues = ("货币资金", "流动资产合计", "资产总计", "负债合计", "所有者权益合计")
        income_cues = ("营业收入", "营业总收入", "营业成本", "营业利润", "净利润", "利润总额")
        cash_cues = (
            "经营活动产生的现金流量净额",
            "投资活动产生的现金流量净额",
            "筹资活动产生的现金流量净额",
        )
        scores = {
            "balance_sheet": sum(1 for cue in balance_cues if cue in content_text),
            "income_statement": sum(1 for cue in income_cues if cue in content_text),
            "cash_flow": sum(1 for cue in cash_cues if cue in content_text),
        }
        best_type, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score >= 2:
            return best_type
        return None

    def _extract_period_headers(
        self,
        table: ParsedTable,
        *,
        report_year: int | None = None,
    ) -> list[str]:
        candidates = [*table.headers]
        header_text = self._normalize_text(" ".join(table.headers))
        header_has_period_cue = any(
            cue in header_text
            for cue in (
                "year ended",
                "years ended",
                "as of",
                "in million",
                "in billion",
                "项目",
                "单位：元",
                "单位:元",
            )
        )
        if not any(self._extract_period_tokens(candidate) for candidate in candidates):
            title_text = self._normalize_text(table.title or "")
            nearby = self._normalize_text(str(table.metadata.get("nearby_context") or ""))
            if any(
                cue in title_text or cue in nearby
                for cue in ("year ended", "years ended", "as of", "年", "月", "日")
            ):
                candidates.append(table.title or "")
                candidates.append(str(table.metadata.get("nearby_context") or ""))

            for row in table.rows[:4]:
                row_periods = self._dedupe_preserve_order(
                    period for cell in row for period in self._extract_period_tokens(cell)
                )
                # Only promote a row that looks like a period header, not equity-history years.
                if len(row_periods) >= 2 and (
                    header_has_period_cue
                    or "项目" in "".join(row)
                    or not row[0].strip()
                    or (len(row) <= 6 and self._row_looks_like_period_header(row))
                ):
                    candidates.extend(row)
                    break

        found: list[str] = []
        for candidate in candidates:
            if self._is_growth_header(candidate):
                continue
            for period in self._extract_period_tokens(candidate):
                if period not in found and self._is_plausible_period(period, report_year=report_year):
                    found.append(period)
        # Keep statement periods tight and drop implausible years from notes/noise.
        year_periods = [period for period in found if re.fullmatch(r"(19|20)\d{2}", period)]
        if year_periods:
            return self._prefer_recent_periods(year_periods, report_year=report_year)[:4]
        return found[:4]

    def _row_looks_like_period_header(self, row: list[str]) -> bool:
        joined = "".join(row)
        if "项目" in joined or "item" in joined.lower():
            return True
        # A real period header is mostly year/date tokens, not metric labels with one year.
        period_cells = sum(1 for cell in row if self._extract_period_tokens(cell))
        return period_cells >= max(2, len([cell for cell in row if str(cell).strip()]) - 1)

    def _prefer_recent_periods(
        self,
        periods: list[str],
        *,
        report_year: int | None,
    ) -> list[str]:
        """Keep table column order; only drop years far from report_year when too many."""
        if not report_year or len(periods) <= 4:
            return periods
        year_periods = [period for period in periods if re.fullmatch(r"(19|20)\d{2}", period)]
        other_periods = [period for period in periods if period not in year_periods]
        if len(year_periods) <= 4:
            return periods
        keep = {
            period
            for period, _distance in sorted(
                ((period, abs(int(period) - report_year)) for period in year_periods),
                key=lambda item: item[1],
            )[:4]
        }
        # Preserve original left-to-right header order for value alignment.
        return [period for period in year_periods if period in keep] + other_periods

    def _is_plausible_period(self, period: str, *, report_year: int | None = None) -> bool:
        if period in {"current_period", "prior_period"}:
            return True
        year_match = re.search(r"(19|20)\d{2}", period)
        if re.search(
            r"(january|february|march|april|may|june|july|august|september|october|november|december)",
            period,
            flags=re.IGNORECASE,
        ) and year_match:
            year = int(year_match.group(0))
            if report_year is not None and (year < report_year - 5 or year > report_year + 1):
                return False
            return 2000 <= year <= 2035
        if not re.fullmatch(r"(19|20)\d{2}", period):
            return False
        year = int(period)
        if not (2000 <= year <= 2035):
            return False
        if report_year is not None and (year < report_year - 5 or year > report_year + 1):
            return False
        return True

    def _recover_statement_header_row(self, table: ParsedTable) -> ParsedTable:
        """Promote Chinese '项目 2021年... 2020年...' rows into headers when needed."""
        if any(self._extract_period_tokens(cell) for cell in table.headers):
            return table
        for index, row in enumerate(table.rows[:3]):
            joined = " ".join(row)
            periods = self._dedupe_preserve_order(
                period for cell in row for period in self._extract_period_tokens(cell)
            )
            if len(periods) >= 2 and ("项目" in joined or "item" in joined.lower()):
                promoted = table.model_copy(deep=True)
                promoted.headers = [cell.strip() for cell in row]
                promoted.rows = table.rows[index + 1 :]
                return promoted
        return table

    def _infer_statement_periods(
        self,
        table: ParsedTable,
        source_section: ParsedSection | None,
        *,
        report_year: int | None = None,
    ) -> list[str]:
        texts = [
            table.title or "",
            str(table.metadata.get("nearby_context") or ""),
            " ".join(table.headers),
            " ".join(" ".join(row[:3]) for row in table.rows[:5]),
            source_section.title if source_section else "",
        ]
        periods: list[str] = []
        for text in texts:
            for period in self._extract_period_tokens(text):
                if (
                    re.fullmatch(r"(19|20)\d{2}", period)
                    and self._is_plausible_period(period, report_year=report_year)
                    and period not in periods
                ):
                    periods.append(period)
        if len(periods) >= 2:
            return self._prefer_recent_periods(periods, report_year=report_year)[:2]
        # Fallback for two-value Chinese statement columns without explicit years.
        numeric_width = 0
        for row in table.rows[:8]:
            values = [cell for cell in row[1:] if self._parse_numeric_value(cell) is not None]
            numeric_width = max(numeric_width, len(values))
        if numeric_width >= 2:
            return ["current_period", "prior_period"][:numeric_width]
        return periods[:2]

    def _extract_period_tokens(self, text: str) -> list[str]:
        date_patterns = re.findall(
            r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\b",
            text,
            flags=re.IGNORECASE,
        )
        if date_patterns:
            periods: list[str] = []
            for period in date_patterns:
                normalized = re.sub(r"\s+", " ", period).strip()
                if normalized not in periods:
                    periods.append(normalized)
            return periods

        chinese_dates = re.findall(r"(20\d{2}|19\d{2})\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日", text)
        if chinese_dates:
            periods = []
            for year in chinese_dates:
                if year not in periods:
                    periods.append(year)
            return periods

        periods = []
        for year in re.findall(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)", text):
            if year not in periods:
                periods.append(year)
        return periods

    def _extract_unit(self, table: ParsedTable, source_section: ParsedSection | None = None) -> str | None:
        text = self._table_context_text(table, source_section)
        for unit, patterns in self._UNIT_PATTERNS:
            if any(pattern in text for pattern in patterns):
                return unit
        return None

    def _extract_currency(self, table: ParsedTable, source_section: ParsedSection | None = None) -> str | None:
        text = self._table_context_text(table, source_section, normalize=False)
        lowered = text.lower()
        if "$" in text or "usd" in lowered or "u.s. dollar" in lowered:
            return "USD"
        if "€" in text or "eur" in lowered:
            return "EUR"
        if (
            "¥" in text
            or "￥" in text
            or "cny" in lowered
            or "rmb" in lowered
            or "人民币" in text
            or "单位：元" in text
            or "单位:元" in text
        ):
            return "CNY"
        return None

    def _table_context_text(
        self,
        table: ParsedTable,
        source_section: ParsedSection | None,
        *,
        normalize: bool = True,
    ) -> str:
        parts = [table.title or "", table.raw_markdown or ""]
        if table.metadata.get("nearby_context"):
            parts.append(str(table.metadata["nearby_context"]))
        if source_section is not None:
            parts.append(source_section.content[:600])
        text = " ".join(part for part in parts if part)
        return self._normalize_text(text) if normalize else text

    def _nearby_block_context(self, table: ParsedTable, page_blocks: list) -> str:
        order_lookup = {
            block.block_id: block.order
            for block in page_blocks
            if block.block_id and block.page == table.page
        }
        table_order = order_lookup.get(table.source_block_id)
        if table_order is None:
            return ""
        nearby = [
            block.text
            for block in page_blocks
            if block.page == table.page
            and block.order is not None
            and 0 < table_order - block.order <= 3
            and block.block_type != "table"
        ]
        return " ".join(nearby[-3:])

    def _promote_embedded_header(self, table: ParsedTable) -> ParsedTable:
        nonempty_headers = [cell.strip() for cell in table.headers if cell.strip()]
        if len(set(nonempty_headers)) > 1 or not table.rows:
            return table

        promoted_index: int | None = None
        for index, row in enumerate(table.rows[:3]):
            distinct = {cell.strip() for cell in row if cell.strip()}
            if len(distinct) >= 3 and any(re.search(r"(?<!\d)(?:19|20)\d{2}(?!\d)", cell) for cell in row):
                promoted_index = index
                break
        if promoted_index is None:
            return table

        promoted = table.model_copy(deep=True)
        promoted.headers = list(promoted.rows[promoted_index])
        promoted.rows = promoted.rows[promoted_index + 1 :]
        promoted.raw_markdown = self._table_to_markdown(promoted.headers, promoted.rows)
        promoted.metadata["embedded_header_promoted"] = True
        promoted.metadata["row_count"] = len(promoted.rows) + 1
        return promoted

    def _inherit_continuation_context(self, tables: list[ParsedTable]) -> list[ParsedTable]:
        inherited: list[ParsedTable] = []
        for table in tables:
            current = table.model_copy(deep=True)
            if inherited:
                previous = inherited[-1]
                same_title = self._normalize_text(previous.title or "") == self._normalize_text(current.title or "")
                if previous.page == current.page and same_title:
                    if not current.period_headers:
                        current.period_headers = list(previous.period_headers)
                    if current.unit is None:
                        current.unit = previous.unit
                    if current.currency is None:
                        current.currency = previous.currency
                    current.metadata["continuation_of_table_id"] = previous.table_id
            inherited.append(current)
        return inherited

    def _merge_cross_page_tables(self, tables: list[ParsedTable]) -> list[ParsedTable]:
        if not tables:
            return []

        ordered = list(tables)
        merged: list[ParsedTable] = [ordered[0]]

        for table in ordered[1:]:
            previous = merged[-1]
            if self._can_merge_tables(previous, table):
                merged[-1] = self._merge_two_tables(previous, table)
            else:
                merged.append(table)

        return merged

    def _can_merge_tables(self, previous: ParsedTable, current: ParsedTable) -> bool:
        if previous.page is None or current.page is None or current.page != previous.page + 1:
            return False
        if previous.table_type != current.table_type:
            return False
        if previous.source_section != current.source_section:
            return False
        if previous.period_headers != current.period_headers:
            return False
        if previous.currency != current.currency or previous.unit != current.unit:
            return False

        previous_title = self._normalize_text(previous.title or "")
        current_title = self._normalize_text(current.title or "")
        if previous_title and current_title and previous_title != current_title:
            return False

        previous_signature = self._header_signature(previous.headers)
        current_signature = self._header_signature(current.headers)
        if previous_signature and current_signature and previous_signature != current_signature:
            return False

        return True

    def _merge_two_tables(self, previous: ParsedTable, current: ParsedTable) -> ParsedTable:
        merged = previous.model_copy(deep=True)
        merged.rows.extend(deepcopy(current.rows))
        if not merged.title and current.title:
            merged.title = current.title
        merged.footnotes = self._dedupe_preserve_order([*merged.footnotes, *current.footnotes])
        if not merged.note_number and current.note_number:
            merged.note_number = current.note_number
        if not merged.note_title and current.note_title:
            merged.note_title = current.note_title
        if not merged.note_category and current.note_category:
            merged.note_category = current.note_category

        page_range = merged.metadata.get("page_range") or [merged.page, merged.page]
        current_range = current.metadata.get("page_range") or [current.page, current.page]
        merged.metadata["page_range"] = [page_range[0], current_range[-1]]
        merged.metadata["merged_from_table_ids"] = self._dedupe_preserve_order(
            [
                *(merged.metadata.get("merged_from_table_ids") or [merged.table_id]),
                current.table_id,
            ]
        )
        merged.metadata["footnote_block_ids"] = self._dedupe_preserve_order(
            [
                *(merged.metadata.get("footnote_block_ids") or []),
                *(current.metadata.get("footnote_block_ids") or []),
            ]
        )
        merged.metadata["row_count"] = len(merged.rows) + (1 if merged.headers else 0)
        merged.raw_markdown = self._table_to_markdown(merged.headers, merged.rows)
        return merged

    def _apply_normalized_metrics(self, table: ParsedTable) -> ParsedTable:
        enhanced = table.model_copy(deep=True)
        if enhanced.table_type == "notes_table":
            enhanced = self._apply_note_semantics(enhanced)
        enhanced.normalized_metrics = self._extract_normalized_metrics(enhanced)
        enhanced.metadata["page_range"] = enhanced.metadata.get("page_range") or [enhanced.page, enhanced.page]
        return enhanced

    def _apply_note_semantics(self, table: ParsedTable) -> ParsedTable:
        note_number, note_title = self._extract_note_identity(table)
        if note_number:
            table.note_number = note_number
        if note_title:
            table.note_title = note_title

        table.note_category = self._classify_note_category(table)
        dimension_headers = self._extract_note_dimension_headers(table)
        if dimension_headers:
            table.metadata["note_dimension_headers"] = dimension_headers
        table.semantic_rows = self._extract_note_semantic_rows(table, dimension_headers=dimension_headers)
        return table

    def _extract_normalized_metrics(self, table: ParsedTable) -> dict[str, Any]:
        aliases = self._METRIC_ALIASES.get(table.table_type or "")
        if not aliases or not table.period_headers:
            return {}

        normalized: dict[str, Any] = {}
        for row in table.rows:
            if not row:
                continue
            compact_label, compact_values = self._split_compact_row(row=row, period_headers=table.period_headers)
            label = self._normalize_row_label(compact_label or row[0])
            if not label:
                continue

            metric_key = self._match_metric_alias(label, aliases)
            if not metric_key:
                continue

            values = self._extract_period_values(
                row=row,
                period_headers=table.period_headers,
                compact_values=compact_values,
            )
            if values:
                normalized[metric_key] = values

        return normalized

    def _match_metric_alias(self, label: str, aliases: dict[str, tuple[str, ...]]) -> str | None:
        matched_metric: str | None = None
        matched_alias_length = -1
        for metric_key, patterns in aliases.items():
            for pattern in patterns:
                if pattern in label and len(pattern) > matched_alias_length:
                    matched_metric = metric_key
                    matched_alias_length = len(pattern)
        return matched_metric

    def _extract_period_values(
        self,
        *,
        row: list[str],
        period_headers: list[str],
        compact_values: list[str] | None = None,
    ) -> dict[str, int | float | str]:
        if compact_values:
            cleaned_values = [self._clean_value_cell(cell) for cell in compact_values]
        else:
            if len(row) <= 1:
                return {}
            cleaned_values = [self._clean_value_cell(cell) for cell in row[1:]]

        cleaned_values = [cell for cell in cleaned_values if cell]
        if not cleaned_values:
            return {}

        parsed_values: list[int | float] = []
        for cell in cleaned_values:
            parsed = self._parse_numeric_value(cell)
            if parsed is not None:
                parsed_values.append(parsed)
        if not parsed_values:
            return {}

        money_values, dropped_ratios = self._drop_ratio_values(parsed_values)
        # When YoY/% columns were removed, keep left-to-right year order.
        # Otherwise keep legacy right-alignment (handles spacer columns).
        if dropped_ratios and len(money_values) >= len(period_headers):
            aligned_values: list[int | float | str] = list(money_values[: len(period_headers)])
        elif len(money_values) >= len(period_headers):
            aligned_values = list(money_values[-len(period_headers) :])
        else:
            aligned_values = [""] * (len(period_headers) - len(money_values)) + list(money_values)

        period_values: dict[str, int | float | str] = {}
        for period, value in zip(period_headers, aligned_values, strict=False):
            if value == "" or value is None:
                continue
            period_values[period] = value

        return period_values

    def _is_growth_header(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False
        return bool(
            re.search(
                r"(同比|环比|增减|变动比例|变动幅度|增长率|增长比例|下降比例|%|％)",
                normalized,
            )
        )

    def _drop_ratio_values(self, values: list[int | float]) -> tuple[list[int | float], bool]:
        """Drop YoY-like percentages when the same row also has monetary amounts."""
        if len(values) < 2:
            return values, False
        large = [value for value in values if abs(float(value)) >= 1000]
        if len(large) < 2:
            return values, False
        filtered = [value for value in values if abs(float(value)) >= 1000]
        if len(filtered) == len(values):
            return values, False
        return filtered, True

    def _split_compact_row(self, *, row: list[str], period_headers: list[str]) -> tuple[str | None, list[str]]:
        if not period_headers:
            return None, []

        # Already-split Chinese financial rows: ["货币资金", "1,607...", "1,204..."]
        # Keep ALL numeric cells so YoY/% columns can be dropped later.
        if len(row) >= 2:
            values = [cell for cell in row[1:] if self._parse_numeric_value(cell) is not None or re.search(r"\d", cell)]
            if len(values) >= min(2, len(period_headers)):
                return row[0].strip() or None, values

        if len(row) != 1:
            return None, []

        text = row[0].strip()
        compact_values = re.findall(
            r"\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\(?-?\d+\.\d{2}\)?",
            text,
        )
        if len(compact_values) < len(period_headers):
            compact_values = re.findall(r"(?:\$\s*)?\(?-?\d[\d,]*(?:\.\d+)?\)?", text)
        if len(compact_values) < len(period_headers):
            return None, []

        label = text
        for value in compact_values:
            label = re.sub(rf"\s*{re.escape(value)}\s*", " ", label, count=1)
        label = label.replace("$", " ")
        label = re.sub(r"\s+", " ", label).strip(" :-")
        return label or None, compact_values

    def _extract_note_identity(self, table: ParsedTable) -> tuple[str | None, str | None]:
        candidates = [
            table.title or "",
            table.metadata.get("source_section_title", ""),
            table.headers[0] if table.headers else "",
        ]
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate.strip():
                continue

            normalized_candidate = self._normalize_note_identity_candidate(candidate)
            match = re.search(
                r"\b(note\s+\d+[a-z]?)\b(?:\s*[-–—:]\s*|\s+)(.+)$",
                normalized_candidate,
                flags=re.IGNORECASE,
            )
            if match:
                return match.group(1).strip(), match.group(2).strip()

            fallback = re.search(r"\b(note\s+\d+[a-z]?)\b", normalized_candidate, flags=re.IGNORECASE)
            if fallback:
                return fallback.group(1).strip(), None

        return None, None

    def _normalize_note_identity_candidate(self, value: str) -> str:
        normalized = value.strip()
        normalized = normalized.replace("鈥?", "-").replace("—", "-").replace("–", "-")
        normalized = normalized.replace("：", ":")
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _classify_note_category(self, table: ParsedTable) -> str:
        candidate_text = " ".join(
            part
            for part in [
                table.note_title or "",
                table.title or "",
                str(table.metadata.get("source_section_title", "") or ""),
                " ".join(table.headers[:3]),
                "\n".join(" | ".join(row[:2]) for row in table.rows[:5]),
            ]
            if part
        )
        normalized = self._normalize_text(candidate_text)
        for category, patterns in self._NOTE_CATEGORY_PATTERNS:
            if any(pattern in normalized for pattern in patterns):
                return category
        return "general_note"

    def _extract_note_dimension_headers(self, table: ParsedTable) -> list[str]:
        if len(table.headers) <= 1:
            return []

        dimension_headers: list[str] = []
        period_candidates = {self._normalize_text(period) for period in table.period_headers}
        for header in table.headers[1:]:
            cleaned = header.strip()
            if not cleaned:
                continue
            normalized_header = self._normalize_text(cleaned)
            if normalized_header in period_candidates:
                continue
            if any(period in normalized_header for period in period_candidates):
                continue
            dimension_headers.append(cleaned)

        return dimension_headers

    def _extract_note_semantic_rows(
        self,
        table: ParsedTable,
        *,
        dimension_headers: list[str],
    ) -> list[dict[str, Any]]:
        semantic_rows: list[dict[str, Any]] = []
        for row in table.rows:
            if not row or not row[0].strip():
                continue

            label = row[0].strip()
            dimension_cells, period_cells = self._split_note_row(table=table, row=row)
            dimension_values = self._build_dimension_value_map(dimension_headers=dimension_headers, dimension_cells=dimension_cells)
            period_values = self._build_period_value_map(period_headers=table.period_headers, period_cells=period_cells)
            tags = self._classify_note_row_tags(label)
            row_type = "metric" if period_values or any(self._parse_numeric_value(cell) is not None for cell in dimension_cells) else "text"

            semantic_rows.append(
                {
                    "label": label,
                    "label_normalized": self._normalize_row_label(label),
                    "row_type": row_type,
                    "dimensions": dimension_values,
                    "period_values": period_values,
                    "tags": tags,
                }
            )

        return semantic_rows

    def _split_note_row(self, *, table: ParsedTable, row: list[str]) -> tuple[list[str], list[str]]:
        cells = row[1:]
        period_count = len(table.period_headers)
        if period_count <= 0:
            return cells, []
        if len(cells) <= period_count:
            padded_period_cells = [""] * (period_count - len(cells)) + cells
            return [], padded_period_cells
        return cells[:-period_count], cells[-period_count:]

    def _build_dimension_value_map(
        self,
        *,
        dimension_headers: list[str],
        dimension_cells: list[str],
    ) -> dict[str, str]:
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

    def _build_period_value_map(
        self,
        *,
        period_headers: list[str],
        period_cells: list[str],
    ) -> dict[str, int | float | str]:
        if not period_headers:
            return {}

        padded_cells = period_cells
        if len(padded_cells) < len(period_headers):
            padded_cells = [""] * (len(period_headers) - len(padded_cells)) + padded_cells
        elif len(padded_cells) > len(period_headers):
            padded_cells = padded_cells[-len(period_headers) :]

        period_values: dict[str, int | float | str] = {}
        for period, value in zip(period_headers, padded_cells, strict=False):
            cleaned = self._clean_value_cell(value)
            if not cleaned:
                continue
            parsed_value = self._parse_numeric_value(cleaned)
            period_values[period] = parsed_value if parsed_value is not None else cleaned
        return period_values

    def _classify_note_row_tags(self, label: str) -> list[str]:
        normalized = self._normalize_row_label(label)
        tags: list[str] = []
        for tag, patterns in self._NOTE_ROW_TAG_PATTERNS:
            if any(pattern in normalized for pattern in patterns):
                tags.append(tag)
        return tags

    def _clean_value_cell(self, value: str) -> str:
        cleaned = value.strip()
        if cleaned in {"$", "€", "¥", "USD", "EUR", "CNY"}:
            return ""
        return cleaned

    def _parse_numeric_value(self, value: str) -> int | float | None:
        cleaned = value.strip()
        if not cleaned:
            return None

        negative = cleaned.startswith("(") and cleaned.endswith(")")
        cleaned = cleaned.strip("()")
        cleaned = cleaned.replace("$", "").replace("€", "").replace("¥", "")
        cleaned = cleaned.replace(",", "").replace("%", "")
        cleaned = re.sub(r"\s+", "", cleaned)
        if not cleaned or not re.search(r"\d", cleaned):
            return None

        try:
            number = float(cleaned)
        except ValueError:
            return None

        if negative:
            number = -number

        return int(number) if number.is_integer() else number

    def _normalize_row_label(self, value: str) -> str:
        normalized = self._normalize_text(value)
        normalized = re.sub(r"\([^)]*\)", " ", normalized)
        normalized = re.sub(r"\b(notes?|footnotes?)\b", " ", normalized)
        normalized = re.sub(r"\bsee\b.*$", " ", normalized)
        normalized = re.sub(r"^[a-z]\.\s+", "", normalized)
        normalized = normalized.replace("less:", " ")
        normalized = normalized.replace("add:", " ")
        normalized = re.sub(r"[\*\u2020]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _header_signature(self, headers: list[str]) -> str:
        return "|".join(self._normalize_text(header) for header in headers if header.strip())

    def _normalize_text(self, text: str) -> str:
        normalized = text.lower()
        normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-")
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _dedupe_preserve_order(self, values: list[Any]) -> list[Any]:
        deduped: list[Any] = []
        for value in values:
            if value and value not in deduped:
                deduped.append(value)
        return deduped

    def _table_to_markdown(self, headers: list[str], rows: list[list[str]]) -> str:
        normalized_rows = []
        if headers:
            normalized_rows.append(headers)
        normalized_rows.extend(rows)
        if not normalized_rows or not normalized_rows[0]:
            return ""

        header = normalized_rows[0]
        divider = ["---"] * len(header)
        markdown_rows = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(divider) + " |",
        ]
        for row in normalized_rows[1:]:
            padded = row + [""] * (len(header) - len(row))
            markdown_rows.append("| " + " | ".join(padded[: len(header)]) + " |")
        return "\n".join(markdown_rows)
