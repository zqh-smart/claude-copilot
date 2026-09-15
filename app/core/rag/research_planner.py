"""Task decomposition for deep research / report-style questions."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchSubtask:
    task_id: str
    question: str
    focus: str
    section_hints: list[str]
    metric_keys: list[str]


_REPORT_CUES = (
    "分析报告",
    "研究报告",
    "全面分析",
    "深度分析",
    "投资价值",
    "是否具有持续性",
    "写一份",
    "生成报告",
    "report",
    "investment thesis",
)
_PROFIT_GROWTH_CUES = ("利润", "盈利", "净利润", "profit", "margin", "毛利")
_REVENUE_CUES = ("营收", "收入", "revenue", "sales")
_RISK_CUES = ("风险", "risk")
_CASH_CUES = ("现金流", "cash flow", "经营现金")
_INDUSTRY_CUES = ("行业", "竞争", "industry", "competition")


def is_deep_research_question(question: str) -> bool:
    normalized = question.casefold()
    if any(cue in normalized for cue in _REPORT_CUES):
        return True
    cue_hits = sum(
        1
        for cues in (_PROFIT_GROWTH_CUES, _REVENUE_CUES, _RISK_CUES, _CASH_CUES)
        if any(cue in normalized for cue in cues)
    )
    return cue_hits >= 3 and len(normalized) >= 24


def plan_deep_research(question: str) -> list[ResearchSubtask]:
    """Break a report-style question into retrieval subtasks."""
    base = re.sub(r"\s+", " ", question).strip()
    tasks: list[ResearchSubtask] = []

    def add(task_id: str, q: str, focus: str, hints: list[str], metrics: list[str]) -> None:
        tasks.append(
            ResearchSubtask(
                task_id=task_id,
                question=q,
                focus=focus,
                section_hints=hints,
                metric_keys=metrics,
            )
        )

    add(
        "revenue_trend",
        f"{base} 重点关注营业收入及同比变化",
        "revenue",
        ["financial_statement", "management_discussion"],
        ["revenue"],
    )
    add(
        "profitability",
        f"{base} 重点关注净利润、毛利率及费用率",
        "profitability",
        ["financial_statement", "management_discussion"],
        ["net_income", "operating_income"],
    )
    add(
        "cash_quality",
        f"{base} 重点关注经营活动现金流量净额及与利润匹配关系",
        "cash",
        ["financial_statement", "management_discussion"],
        ["net_cash_from_operating_activities"],
    )
    add(
        "growth_drivers",
        f"{base} 管理层如何解释主营业务增长或变化的驱动因素",
        "mda_drivers",
        ["management_discussion"],
        [],
    )
    add(
        "risks",
        f"{base} 公司披露的主要经营与市场风险",
        "risk",
        ["risk_section"],
        [],
    )
    if any(cue in base.casefold() for cue in _INDUSTRY_CUES):
        add(
            "industry_context",
            f"{base} 行业环境、竞争格局与业务板块",
            "industry",
            ["management_discussion", "company_overview"],
            [],
        )
    return tasks
