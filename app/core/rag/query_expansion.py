class QueryExpansionService:
    """Lightweight bilingual query expansion for hybrid retrieval."""

    _EXPANSION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
        (("管理层", "md&a", "经营情况", "讨论与分析"), "管理层讨论与分析 经营分析"),
        (("风险", "risk", "暴露"), "风险因素 风险披露"),
        (("营收", "收入", "revenue"), "营业收入 主营业务收入"),
        (("增长", "同比", "cagr", "趋势"), "同比增长 增长率"),
        (("现金流", "cash flow"), "经营活动产生的现金流量净额"),
        (("行业", "industry"), "所处行业 行业地位"),
        (("子公司", "分部", "segment"), "业务板块 子公司"),
    )

    def expand(self, question: str, n: int = 4) -> list[str]:
        seeds = [question.strip()]
        normalized = question.casefold()
        for cues, suffix in self._EXPANSION_RULES:
            if any(cue in normalized for cue in cues):
                seeds.append(f"{question} {suffix}")
        return list(dict.fromkeys(item for item in seeds[:n] if item))
