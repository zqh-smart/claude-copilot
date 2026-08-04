from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.core.db import FinancialDataRepositoryProtocol
from app.core.db.serving_facts import (
    candidate_from_observation,
    metric_values_conflict,
    normalize_metric_value,
    resolve_metric_conflict,
)
from app.core.kg import KnowledgeGraphStoreProtocol
from app.core.rag.retriever import LocalRetriever
from src.claude_copilot.entity_resolution import EntityResolver
from src.claude_copilot.schemas.financial_data import FinancialMetricObservation
from src.claude_copilot.schemas.knowledge_graph import GraphPath
from src.claude_copilot.schemas.research import FusionSummary, MetricCalculation, QueryAnalysis

# Alias groups for joint-benchmark cross-company abstain (fallback when repo catalog is thin).
# Matching any alias in a group treats the whole group as that company identity.
_WELL_KNOWN_COMPANY_GROUPS: tuple[tuple[str, ...], ...] = (
    ("北京指南针科技发展股份有限公司", "指南针", "300803"),
    ("聚灿光电科技股份有限公司", "聚灿光电", "300708"),
    ("苏州天华新能源科技股份有限公司", "天华新能", "天华超净", "300390"),
    ("湖北共同药业股份有限公司", "共同药业", "300966"),
    ("广州市浪奇实业股份有限公司", "广州浪奇", "浪奇", "000523"),
    ("浙江核新同花顺网络信息股份有限公司", "同花顺", "300033"),
    ("深圳顺络电子股份有限公司", "顺络电子", "002138"),
    ("江苏爱朋医疗科技股份有限公司", "爱朋医疗", "300753"),
    ("浙江运达风电股份有限公司", "运达股份", "运达风电", "300772"),
    ("江苏博云塑业股份有限公司", "江苏博云", "博云塑业", "301003"),
    ("上海能辉科技股份有限公司", "能辉科技", "301046"),
    ("东鹏饮料集团股份有限公司", "东鹏饮料", "东鹏特饮", "605499"),
    ("中科创达软件股份有限公司", "中科创达", "300496"),
    ("Apple Inc.", "Apple", "AAPL"),
    ("JPMorgan Chase & Co.", "JPMorgan", "JPM"),
    ("华衡科技股份有限公司", "华衡科技"),
)


@dataclass
class OrchestratedRetrievalResult:
    analysis: QueryAnalysis
    vector_hits: list[tuple] = field(default_factory=list)
    metrics: list[FinancialMetricObservation] = field(default_factory=list)
    calculations: list[MetricCalculation] = field(default_factory=list)
    graph_paths: list[GraphPath] = field(default_factory=list)
    fusion_summary: FusionSummary | None = None
    warnings: list[str] = field(default_factory=list)


class QueryAnalyzer:
    _METRIC_ALIASES: dict[str, tuple[str, ...]] = {
        "revenue": (
            "revenue",
            "net revenue",
            "total revenue",
            "营收",
            "营业收入",
            "收入",
        ),
        "net_income": ("net income", "net profit", "净利润", "净收益"),
        "total_assets": ("total assets", "总资产"),
        "total_liabilities": ("total liabilities", "总负债"),
        "total_equity": ("total equity", "shareholders' equity", "股东权益", "净资产"),
        "interest_income": ("interest income", "利息收入"),
        "net_interest_income": ("net interest income", "净利息收入"),
        "operating_income": ("operating income", "营业利润"),
        "net_cash_from_operating_activities": (
            "operating cash flow",
            "cash from operating activities",
            "经营活动产生的现金流量净额",
            "经营活动现金流量净额",
            "经营现金流",
            "经营活动现金流",
        ),
        "earnings_per_share_basic": ("basic earnings per share", "basic eps", "基本每股收益"),
        "earnings_per_share_diluted": (
            "diluted earnings per share",
            "diluted eps",
            "稀释每股收益",
        ),
    }
    _SEMANTIC_CUES = (
        "why",
        "how",
        "reason",
        "driver",
        "risk",
        "outlook",
        "management",
        "explain",
        "analyze",
        "为什么",
        "原因",
        "驱动",
        "风险",
        "展望",
        "管理层",
        "如何",
        "分析",
    )
    _STRUCTURED_CUES = (
        "how much",
        "amount",
        "ratio",
        "trend",
        "growth",
        "cagr",
        "yoy",
        "多少",
        "数值",
        "金额",
        "比率",
        "趋势",
        "增长",
        "同比",
        "复合增长",
    )
    _GROWTH_CUES = ("growth", "trend", "cagr", "yoy", "增长", "同比", "趋势", "复合增长")
    _GRAPH_CUES = (
        "risk",
        "relationship",
        "related",
        "exposure",
        "affect",
        "subsidiary",
        "industry",
        "segment",
        "competitor",
        "风险",
        "关系",
        "关联",
        "暴露",
        "影响",
        "子公司",
        "行业",
        "业务板块",
        "分部",
        "竞争对手",
    )
    _DISCLOSURE_SEGMENT_CUES = (
        "reportable segment",
        "geographic segment",
        "segment information",
        "segment reporting",
        "可报告分部",
        "地区分部",
        "分部信息",
    )
    _SECTION_HINTS: dict[str, tuple[str, ...]] = {
        "management_discussion": (
            "管理层",
            "讨论与分析",
            "md&a",
            "经营情况",
            "management",
            "mda",
        ),
        "risk_section": ("风险", "risk", "暴露"),
        "company_overview": ("公司简介", "公司概况", "overview", "基本情况"),
        "financial_statement": (
            "利润表",
            "资产负债表",
            "现金流量",
            "income statement",
            "balance sheet",
            "cash flow statement",
        ),
    }

    def analyze(self, question: str) -> QueryAnalysis:
        normalized = re.sub(r"\s+", " ", question).strip().casefold()
        matched_aliases = [
            (metric_key, alias)
            for metric_key, aliases in self._METRIC_ALIASES.items()
            for alias in aliases
            if alias in normalized
        ]
        metric_keys = []
        for metric_key, alias in matched_aliases:
            shadowed = any(
                other_metric != metric_key
                and alias in other_alias
                and len(other_alias) > len(alias)
                for other_metric, other_alias in matched_aliases
            )
            if not shadowed and metric_key not in metric_keys:
                metric_keys.append(metric_key)
        years = sorted(
            {int(year) for year in re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", normalized)}
        )
        has_semantic_cue = any(cue in normalized for cue in self._SEMANTIC_CUES)
        has_structured_cue = any(cue in normalized for cue in self._STRUCTURED_CUES)
        needs_growth = any(cue in normalized for cue in self._GROWTH_CUES)
        wants_graph = any(cue in normalized for cue in self._GRAPH_CUES) and not any(
            cue in normalized for cue in self._DISCLOSURE_SEGMENT_CUES
        )
        section_hints = self._infer_section_hints(normalized)

        wants_structured = bool(metric_keys or years or has_structured_cue)
        if wants_graph and (wants_structured or has_semantic_cue):
            intent = "hybrid"
            routes = ["vector"]
            if wants_structured:
                routes.append("sql")
            routes.append("graph")
        elif wants_graph:
            intent = "relational"
            routes = ["graph"]
        elif wants_structured and has_semantic_cue:
            intent = "hybrid"
            routes = ["vector", "sql"]
        elif wants_structured:
            intent = "structured"
            routes = ["sql"]
        else:
            intent = "semantic"
            routes = ["vector"]

        return QueryAnalysis(
            intent=intent,
            routes=routes,
            metric_keys=metric_keys,
            years=years,
            needs_growth=needs_growth,
            section_hints=section_hints,
        )

    def _infer_section_hints(self, normalized: str) -> list[str]:
        hints: list[str] = []
        for section_type, cues in self._SECTION_HINTS.items():
            if any(cue in normalized for cue in cues):
                hints.append(section_type)
        return hints


class RetrievalOrchestrator:
    def __init__(
        self,
        *,
        vector_retriever: LocalRetriever,
        financial_repository: FinancialDataRepositoryProtocol,
        graph_store: KnowledgeGraphStoreProtocol | None = None,
        query_analyzer: QueryAnalyzer | None = None,
    ) -> None:
        self._vector_retriever = vector_retriever
        self._financial_repository = financial_repository
        self._graph_store = graph_store
        self._query_analyzer = query_analyzer or QueryAnalyzer()

    def retrieve(
        self,
        question: str,
        *,
        doc_id: str,
        company_id: str | None,
        top_k: int,
        routes_override: list[str] | None = None,
        company_name: str | None = None,
        company_aliases: list[str] | None = None,
    ) -> OrchestratedRetrievalResult:
        analysis = self._query_analyzer.analyze(question)
        if routes_override is not None:
            # Eval-only channel ablation: keep analyzer intent/metrics, force active routes.
            analysis = analysis.model_copy(update={"routes": list(routes_override)})
        vector_hits = []
        metrics: list[FinancialMetricObservation] = []
        warnings: list[str] = []
        graph_paths: list[GraphPath] = []

        foreign_company = self._detect_foreign_company_mention(
            question,
            company_name=company_name,
            company_aliases=company_aliases or [],
        )
        if foreign_company:
            warnings.append(
                "Company scope mismatch: question mentions "
                f"「{foreign_company}」but pinned document is "
                f"「{company_name or company_id or doc_id}」. "
                "SQL/graph abstained."
            )

        if "vector" in analysis.routes:
            vector_hits = self._vector_retriever.retrieve(
                question,
                doc_id=doc_id,
                top_k=top_k,
                section_hints=analysis.section_hints,
                metric_keys=list(analysis.metric_keys or []),
            )

        if "sql" in analysis.routes:
            if foreign_company:
                warnings.append("SQL route skipped due to company scope mismatch")
            elif company_id is None:
                warnings.append("SQL route skipped because the document has no company metadata")
            else:
                metrics = self._retrieve_metrics(
                    company_id,
                    analysis=analysis,
                    top_k=top_k,
                    document_id=doc_id,
                )
                if not metrics:
                    warnings.append(
                        "SQL route returned no matching financial metrics "
                        f"(doc_id={doc_id[:12]}…; prefer a Serving-ingested annual report)"
                    )
                elif doc_id and not any(item.document_id == doc_id for item in metrics):
                    warnings.append(
                        "SQL metrics resolved from company scope; "
                        f"none tagged doc_id={doc_id[:12]}…"
                    )

        if "graph" in analysis.routes:
            if foreign_company:
                warnings.append("Graph route skipped due to company scope mismatch")
            elif self._graph_store is None:
                warnings.append("Graph route skipped because no graph store is configured")
            else:
                graph_paths = self._graph_store.search(
                    question,
                    document_id=None if company_id else doc_id,
                    company_id=company_id,
                    limit=top_k,
                )
                if not graph_paths:
                    warnings.append("Graph route returned no matching relationships")

        calculations, calculation_warnings = self._calculate(metrics)
        warnings.extend(calculation_warnings)
        fusion_summary = self._build_fusion_summary(
            analysis=analysis,
            vector_hits=vector_hits,
            metrics=metrics,
            calculations=calculations,
            graph_paths=graph_paths,
        )
        return OrchestratedRetrievalResult(
            analysis=analysis,
            vector_hits=vector_hits,
            metrics=metrics,
            calculations=calculations,
            graph_paths=graph_paths,
            fusion_summary=fusion_summary,
            warnings=warnings,
        )

    def _aliases_compatible_with_company(self, company_name: str, alias: str) -> bool:
        """Drop polluted aliases that do not belong to the pinned company identity."""
        resolver = EntityResolver()
        company_key = resolver.canonical_key(company_name)
        alias_key = resolver.canonical_key(alias)
        if not company_key or company_key == "company":
            return False
        if alias.casefold() == company_name.casefold() or alias_key == company_key:
            return True
        if len(alias_key) >= 2 and (
            alias_key in company_key or company_key in alias_key
        ):
            return True
        for group in _WELL_KNOWN_COMPANY_GROUPS:
            group_fold = {member.casefold() for member in group}
            group_keys = {resolver.canonical_key(member) for member in group}
            company_in_group = (
                company_name.casefold() in group_fold
                or company_key in group_keys
                or any(
                    len(member_key) >= 2
                    and (member_key in company_key or company_key in member_key)
                    for member_key in group_keys
                )
            )
            alias_in_group = alias.casefold() in group_fold or alias_key in group_keys
            if company_in_group and alias_in_group:
                return True
        return False

    def _detect_foreign_company_mention(
        self,
        question: str,
        *,
        company_name: str | None,
        company_aliases: list[str],
    ) -> str | None:
        """If the question names another company than the pinned doc, return that mention."""
        trusted_aliases = list(company_aliases)
        if company_name and str(company_name).strip():
            trusted_aliases = [
                alias
                for alias in company_aliases
                if alias
                and str(alias).strip()
                and self._aliases_compatible_with_company(str(company_name), str(alias))
            ]
        pinned = [
            name
            for name in (company_name, *trusted_aliases)
            if name and str(name).strip()
        ]
        if not pinned:
            return None

        resolver = EntityResolver()
        pinned_keys = {resolver.canonical_key(name) for name in pinned if len(name) >= 2}
        pinned_fold = {name.casefold() for name in pinned}

        def _same_company(alias: str) -> bool:
            alias_key = resolver.canonical_key(alias)
            if not alias_key or alias_key == "company":
                return False
            if alias.casefold() in pinned_fold or alias_key in pinned_keys:
                return True
            return any(
                pinned_key in alias_key or alias_key in pinned_key
                for pinned_key in pinned_keys
                if len(pinned_key) >= 2
            )

        groups: list[tuple[str, ...]] = [tuple(group) for group in _WELL_KNOWN_COMPANY_GROUPS]
        try:
            for company in self._financial_repository.list_companies():
                name = getattr(company, "name", None)
                if name and str(name).strip():
                    groups.append((str(name).strip(),))
        except Exception:  # noqa: BLE001
            pass

        # Prefer longer surface forms so legal names beat short tickers/fragments.
        scored: list[tuple[int, str, tuple[str, ...]]] = []
        for group in groups:
            for alias in group:
                cleaned = alias.strip()
                if len(cleaned) < 2:
                    continue
                scored.append((len(cleaned), cleaned, group))
        scored.sort(key=lambda item: item[0], reverse=True)

        question_fold = question.casefold()
        for _, alias, group in scored:
            if alias not in question and alias.casefold() not in question_fold:
                continue
            if _same_company(alias) or any(_same_company(member) for member in group):
                continue
            return alias
        return None

    def _build_fusion_summary(
        self,
        *,
        analysis: QueryAnalysis,
        vector_hits: list[tuple],
        metrics: list[FinancialMetricObservation],
        calculations: list[MetricCalculation],
        graph_paths: list[GraphPath],
    ) -> FusionSummary:
        highlights: list[str] = []

        for segment, score in vector_hits[:3]:
            section_type = (segment.metadata or {}).get("section_type")
            prefix = f"[语义·{section_type}]" if section_type else "[语义]"
            snippet = segment.content.strip().replace("\n", " ")[:120]
            highlights.append(f"{prefix} {snippet} (score={score:.3f})")

        seen_metric_keys: set[tuple[str, str]] = set()
        for item in metrics[:8]:
            key = (item.metric_key, str(item.period))
            if key in seen_metric_keys:
                continue
            seen_metric_keys.add(key)
            highlights.append(f"[结构化] {item.metric_key} · {item.period} = {item.value}")

        for calc in calculations[:3]:
            if calc.yoy_growth:
                latest_year = max(calc.yoy_growth)
                rate = calc.yoy_growth[latest_year]
                highlights.append(f"[计算] {calc.metric_key} YoY({latest_year}) = {rate:.2%}")
            elif calc.cagr is not None:
                highlights.append(f"[计算] {calc.metric_key} CAGR = {calc.cagr:.2%}")

        for path in graph_paths[:3]:
            highlights.append(f"[图谱] {path.summary}")

        route_labels = {
            "vector": "语义片段",
            "sql": "结构化指标",
            "graph": "关系路径",
        }
        active = [route_labels.get(route, route) for route in analysis.routes]
        summary_parts = [
            f"意图={analysis.intent}，启用通道：{' + '.join(active) or '无'}。",
            (
                f"召回：语义 {len(vector_hits)} 条、指标 {len(metrics)} 条、"
                f"图谱 {len(graph_paths)} 条。"
            ),
        ]
        if highlights:
            summary_parts.append(f"要点：{'；'.join(highlights[:4])}。")

        return FusionSummary(
            query_intent=analysis.intent,
            routes=list(analysis.routes),
            vector_snippet_count=len(vector_hits),
            metric_count=len(metrics),
            graph_path_count=len(graph_paths),
            highlights=highlights,
            summary="".join(summary_parts),
        )

    def _retrieve_metrics(
        self,
        company_id: str,
        *,
        analysis: QueryAnalysis,
        top_k: int,
        document_id: str | None = None,
    ) -> list[FinancialMetricObservation]:
        observations: list[FinancialMetricObservation] = []
        metric_keys = analysis.metric_keys or [None]
        for metric_key in metric_keys:
            observations.extend(
                self._financial_repository.query_metrics(
                    company_id,
                    year=analysis.years[0] if len(analysis.years) == 1 else None,
                    metric_key=metric_key,
                    document_id=document_id,
                    limit=max(20, top_k * 10),
                )
            )
        if not observations and document_id is not None:
            for metric_key in metric_keys:
                observations.extend(
                    self._financial_repository.query_metrics(
                        company_id,
                        year=analysis.years[0] if len(analysis.years) == 1 else None,
                        metric_key=metric_key,
                        document_id=None,
                        limit=max(20, top_k * 10),
                    )
                )
        if len(analysis.years) > 1:
            year_filter = set(analysis.years)
            observations = [item for item in observations if item.period_year in year_filter]
        return observations

    def _calculate(
        self,
        observations: list[FinancialMetricObservation],
    ) -> tuple[list[MetricCalculation], list[str]]:
        grouped: dict[str, dict[int, list[FinancialMetricObservation]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for item in observations:
            if (
                item.period_year is not None
                and isinstance(item.value, (int, float))
                and not isinstance(item.value, bool)
            ):
                grouped[item.metric_key][item.period_year].append(item)

        calculations: list[MetricCalculation] = []
        warnings: list[str] = []
        for metric_key, by_year in grouped.items():
            yearly_values: dict[int, float] = {}
            for year, candidates in sorted(by_year.items()):
                distinct_values = {normalize_metric_value(item.value) for item in candidates}
                if len(distinct_values) > 1:
                    period = candidates[0].period
                    resolution = resolve_metric_conflict(
                        [candidate_from_observation(item) for item in candidates],
                        metric_key=metric_key,
                        period=period,
                    )
                    warnings.extend(resolution.warnings)
                    winner = next(
                        (
                            item
                            for item in candidates
                            if resolution.winner is not None
                            and item.document_id == resolution.winner.document_id
                            and not metric_values_conflict(item.value, resolution.winner.value)
                        ),
                        candidates[0],
                    )
                    yearly_values[year] = float(winner.value)
                    continue
                yearly_values[year] = float(candidates[0].value)

            yoy_growth = {}
            years = sorted(yearly_values)
            for previous_year, current_year in zip(years, years[1:], strict=False):
                previous = yearly_values[previous_year]
                if previous != 0:
                    yoy_growth[current_year] = round(
                        (yearly_values[current_year] - previous) / abs(previous),
                        6,
                    )

            cagr = None
            if len(years) >= 2:
                first_year, last_year = years[0], years[-1]
                first_value, last_value = yearly_values[first_year], yearly_values[last_year]
                if first_value > 0 and last_value > 0 and last_year > first_year:
                    cagr = round(
                        (last_value / first_value) ** (1 / (last_year - first_year)) - 1,
                        6,
                    )
            calculations.append(
                MetricCalculation(
                    metric_key=metric_key,
                    yearly_values=yearly_values,
                    yoy_growth=yoy_growth,
                    cagr=cagr,
                )
            )
        return calculations, warnings
