"""LangGraph Comparator Agent — dual-document metric matrix (no LLM)."""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from app.core.db.financial_data_repository import extract_period_year


class ComparatorState(TypedDict, total=False):
    doc_id_a: str
    doc_id_b: str
    company_a: str | None
    company_b: str | None
    metric_keys: list[str]
    period: str | int
    question: str
    metrics_a: list[dict]
    metrics_b: list[dict]
    matrix: list[dict]
    highlights: list[str]
    warnings: list[str]
    answer: str


class _FallbackComparatorGraph:
    def __init__(
        self,
        load_fn: Callable[[dict], dict],
        build_fn: Callable[[dict], dict],
        format_fn: Callable[[dict], dict],
    ) -> None:
        self._load_fn = load_fn
        self._build_fn = build_fn
        self._format_fn = format_fn

    def invoke(self, state: dict) -> dict:
        updated = {**state, **self._load_fn(state)}
        updated = {**updated, **self._build_fn(updated)}
        return {**updated, **self._format_fn(updated)}


def _metric_numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _period_matches(item: dict, period: str | int | None) -> bool:
    if period is None:
        return True
    if isinstance(period, int):
        return item.get("period_year") == period
    period_str = str(period)
    return (
        str(item.get("period") or "") == period_str
        or str(item.get("period_year") or "") == period_str
    )


def normalize_metric_facts(facts: list[Any] | None) -> list[dict]:
    """Normalize FinancialMetricFact objects or dicts; dedupe by (metric_key, period)."""
    if not facts:
        return []

    best: dict[tuple[str, str], dict] = {}
    for fact in facts:
        if hasattr(fact, "model_dump"):
            raw = fact.model_dump(mode="json")
        elif isinstance(fact, dict):
            raw = fact
        else:
            continue

        metric_key = str(raw.get("metric_key") or "")
        period = str(raw.get("period") or "")
        if not metric_key:
            continue

        period_year = raw.get("period_year")
        if period_year is None:
            period_year = extract_period_year(period)

        normalized = {
            "metric_key": metric_key,
            "period": period,
            "period_year": period_year,
            "value": raw.get("value"),
            "unit": raw.get("unit"),
            "currency": raw.get("currency"),
        }
        slot = (metric_key, period)
        prev = best.get(slot)
        if prev is None:
            best[slot] = normalized
            continue
        prev_num = _metric_numeric_value(prev.get("value"))
        cur_num = _metric_numeric_value(normalized.get("value"))
        if cur_num is not None and (prev_num is None or abs(cur_num) > abs(prev_num)):
            best[slot] = normalized

    return list(best.values())


def build_comparison_matrix(
    metrics_a: list[dict],
    metrics_b: list[dict],
    metric_keys: list[str] | None = None,
    period: str | int | None = None,
) -> list[dict]:
    """Join metrics on (metric_key, period) and compute delta / delta_pct."""
    allowed_keys = set(metric_keys) if metric_keys else None

    def _filter(items: list[dict]) -> list[dict]:
        filtered: list[dict] = []
        for item in items:
            key = str(item.get("metric_key") or "")
            if not key:
                continue
            if allowed_keys is not None and key not in allowed_keys:
                continue
            if not _period_matches(item, period):
                continue
            filtered.append(item)
        return filtered

    filtered_a = _filter(metrics_a)
    filtered_b = _filter(metrics_b)

    index_a = {(str(item["metric_key"]), str(item.get("period") or "")): item for item in filtered_a}
    index_b = {(str(item["metric_key"]), str(item.get("period") or "")): item for item in filtered_b}

    rows: list[dict] = []
    for slot in sorted(set(index_a) | set(index_b)):
        item_a = index_a.get(slot)
        item_b = index_b.get(slot)
        value_a = item_a.get("value") if item_a else None
        value_b = item_b.get("value") if item_b else None

        num_a = _metric_numeric_value(value_a)
        num_b = _metric_numeric_value(value_b)
        delta: float | None = None
        delta_pct: float | None = None
        if num_a is not None and num_b is not None:
            delta = round(num_b - num_a, 6)
            if num_a != 0:
                delta_pct = round(delta / abs(num_a), 6)

        rows.append(
            {
                "metric_key": slot[0],
                "period": slot[1],
                "value_a": value_a,
                "value_b": value_b,
                "delta": delta,
                "delta_pct": delta_pct,
            }
        )

    return rows


def _compute_highlights(matrix: list[dict], limit: int = 3) -> list[str]:
    candidates: list[tuple[float, dict]] = []
    for row in matrix:
        delta_pct = row.get("delta_pct")
        if delta_pct is None:
            continue
        candidates.append((abs(float(delta_pct)), row))
    candidates.sort(key=lambda item: item[0], reverse=True)

    highlights: list[str] = []
    for _, row in candidates[:limit]:
        pct = float(row["delta_pct"]) * 100
        highlights.append(
            f"{row['metric_key']} ({row['period']}): 相对差异 {pct:.2f}%"
        )
    return highlights


def format_comparison_answer(
    matrix: list[dict],
    company_a: str | None,
    company_b: str | None,
    highlights: list[str],
    warnings: list[str],
) -> str:
    label_a = company_a or "文档 A"
    label_b = company_b or "文档 B"
    parts: list[str] = [f"# {label_a} vs {label_b} 指标对比"]

    if matrix:
        parts.append("\n## 对比矩阵")
        for row in matrix:
            metric_key = row.get("metric_key") or "unknown"
            period_label = row.get("period") or "—"
            value_a = row.get("value_a")
            value_b = row.get("value_b")
            delta = row.get("delta")
            delta_pct = row.get("delta_pct")

            line = f"- {metric_key} ({period_label}): {label_a}={value_a}, {label_b}={value_b}"
            if delta is not None:
                line += f", 差异={delta:,.4g}"
            if delta_pct is not None:
                line += f" ({delta_pct * 100:.2f}%)"
            parts.append(line)
    else:
        parts.append("\n无可对比的结构化指标。")

    if highlights:
        parts.append("\n## 显著差异")
        for item in highlights:
            parts.append(f"- {item}")

    if warnings:
        parts.append("\n## 说明")
        for warning in warnings[:6]:
            parts.append(f"- {warning}")

    return "\n".join(parts).strip()


def _load_doc_metrics(doc_id: str) -> tuple[str | None, list[dict], list[str]]:
    from app.api.dependencies import get_document_pipeline_service, get_parsed_document_repository

    warnings: list[str] = []
    record = get_document_pipeline_service().get_document(doc_id)
    company = record.metadata.company

    parsed = get_parsed_document_repository().get(doc_id)
    schema = parsed.financial_schema if parsed is not None else None
    if schema is None:
        warnings.append(f"文档 {doc_id} 缺少 financial_schema，无法加载指标。")
        return company, [], warnings

    facts = schema.metric_facts or []
    if not facts:
        warnings.append(f"文档 {doc_id} 无 metric_facts。")

    return company, normalize_metric_facts(facts), warnings


def _default_load_metrics(state: dict) -> dict:
    doc_id_a = state["doc_id_a"]
    doc_id_b = state["doc_id_b"]

    company_a, metrics_a, warnings_a = _load_doc_metrics(doc_id_a)
    company_b, metrics_b, warnings_b = _load_doc_metrics(doc_id_b)

    return {
        "company_a": state.get("company_a") or company_a,
        "company_b": state.get("company_b") or company_b,
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "warnings": [*list(state.get("warnings") or []), *warnings_a, *warnings_b],
    }


def _default_build_matrix(state: dict) -> dict:
    metrics_a = list(state.get("metrics_a") or [])
    metrics_b = list(state.get("metrics_b") or [])
    metric_keys = state.get("metric_keys")
    period = state.get("period")
    warnings = list(state.get("warnings") or [])

    matrix = build_comparison_matrix(metrics_a, metrics_b, metric_keys=metric_keys, period=period)

    index_a = {(str(item["metric_key"]), str(item.get("period") or "")) for item in metrics_a}
    index_b = {(str(item["metric_key"]), str(item.get("period") or "")) for item in metrics_b}
    only_a = index_a - index_b
    only_b = index_b - index_a
    if only_a:
        warnings.append(f"文档 B 缺少 {len(only_a)} 个 (metric_key, period) 组合。")
    if only_b:
        warnings.append(f"文档 A 缺少 {len(only_b)} 个 (metric_key, period) 组合。")

    highlights = _compute_highlights(matrix)
    return {"matrix": matrix, "highlights": highlights, "warnings": warnings}


def _default_format_answer(state: dict) -> dict:
    answer = format_comparison_answer(
        matrix=list(state.get("matrix") or []),
        company_a=state.get("company_a"),
        company_b=state.get("company_b"),
        highlights=list(state.get("highlights") or []),
        warnings=list(state.get("warnings") or []),
    )
    return {"answer": answer}


def build_comparator_graph(
    load_fn: Callable[[dict], dict] | None = None,
    build_fn: Callable[[dict], dict] | None = None,
    format_fn: Callable[[dict], dict] | None = None,
):
    load_metrics = load_fn or _default_load_metrics
    build_matrix = build_fn or _default_build_matrix
    format_answer = format_fn or _default_format_answer
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return _FallbackComparatorGraph(load_metrics, build_matrix, format_answer)

    builder = StateGraph(ComparatorState)
    builder.add_node("load_metrics", load_metrics)
    builder.add_node("build_matrix", build_matrix)
    builder.add_node("format_answer", format_answer)
    builder.add_edge(START, "load_metrics")
    builder.add_edge("load_metrics", "build_matrix")
    builder.add_edge("build_matrix", "format_answer")
    builder.add_edge("format_answer", END)
    return builder.compile()


graph = build_comparator_graph()
