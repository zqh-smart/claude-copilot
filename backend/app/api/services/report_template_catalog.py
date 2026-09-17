"""Built-in financial report templates: chapters + evidence + writing rules."""

from __future__ import annotations

from src.claude_copilot.schemas.report_studio import ReportTemplate, ReportTemplateChapter


def _ch(
    chapter_id: str,
    title: str,
    *,
    hints: list[str],
    metrics: list[str] | None = None,
    sections: list[str] | None = None,
    rules: list[str] | None = None,
    must_cite: bool = True,
) -> ReportTemplateChapter:
    return ReportTemplateChapter(
        chapter_id=chapter_id,
        title=title,
        hints=hints,
        required_metrics=metrics or [],
        section_hints=sections or [],
        analysis_requirements=rules or [],
        must_cite=must_cite,
    )


_COMPARE = ["当前期与上一期对比", "判断升降幅度", "查找管理层解释", "区分事实与模型推断"]


def list_report_templates() -> list[ReportTemplate]:
    return [
        ReportTemplate(
            template_id="comprehensive_financial",
            name="综合财务分析报告",
            category="综合分析",
            scenario="最通用，分析单家公司年度/季度经营财务情况",
            description="适合年度综合分析",
            chapters=[
                _ch("exec_summary", "执行摘要", hints=["摘要", "结论"], rules=["概括核心指标与结论"], must_cite=False),
                _ch("company", "公司及报告期概况", hints=["公司", "文档", "概况"], sections=["company_overview"], metrics=["revenue"]),
                _ch(
                    "core_metrics",
                    "核心财务指标",
                    hints=["财务", "指标"],
                    metrics=["revenue", "net_income", "total_assets", "total_liabilities"],
                    sections=["financial_statement"],
                    rules=_COMPARE,
                ),
                _ch(
                    "profitability",
                    "盈利能力分析",
                    hints=["利润", "盈利", "毛利"],
                    metrics=["revenue", "gross_profit", "operating_income", "net_income"],
                    sections=["financial_statement", "management_discussion"],
                    rules=_COMPARE,
                ),
                _ch(
                    "operations",
                    "营运能力分析",
                    hints=["营运", "周转"],
                    metrics=["revenue", "total_assets"],
                    sections=["financial_statement", "notes"],
                    rules=_COMPARE,
                ),
                _ch(
                    "solvency",
                    "偿债能力分析",
                    hints=["偿债", "负债"],
                    metrics=["total_assets", "total_liabilities", "total_equity"],
                    sections=["financial_statement"],
                    rules=_COMPARE,
                ),
                _ch(
                    "cash_flow",
                    "现金流分析",
                    hints=["现金", "现金流"],
                    metrics=["net_cash_from_operating_activities", "net_income"],
                    sections=["financial_statement", "management_discussion"],
                    rules=["现金流与利润是否匹配", *_COMPARE],
                ),
                _ch(
                    "growth",
                    "成长能力分析",
                    hints=["增长", "趋势", "成长"],
                    metrics=["revenue", "net_income"],
                    sections=["management_discussion"],
                    rules=["给出同比变化并寻找驱动解释"],
                ),
                _ch(
                    "anomalies",
                    "财务异常与风险",
                    hints=["异常", "风险"],
                    sections=["risk_section", "management_discussion"],
                    rules=["列出异常变动并引用披露"],
                ),
                _ch("conclusion", "综合评价与结论", hints=["结论", "建议", "摘要"], rules=["综合前文章节，不新增未引用数字"], must_cite=False),
            ],
        ),
        ReportTemplate(
            template_id="annual_operations",
            name="年度经营分析报告",
            category="经营分析",
            scenario="年报、经营分析会、管理层汇报",
            description="聚焦经营变化",
            chapters=[
                _ch("exec_summary", "执行摘要", hints=["摘要"], must_cite=False),
                _ch("overview", "年度经营概况", hints=["公司", "概况", "经营"], sections=["management_discussion", "company_overview"]),
                _ch(
                    "revenue_mix",
                    "收入与业务结构",
                    hints=["收入", "营收", "业务"],
                    metrics=["revenue"],
                    sections=["management_discussion", "financial_statement"],
                    rules=_COMPARE,
                ),
                _ch(
                    "costs",
                    "成本费用",
                    hints=["成本", "费用"],
                    metrics=["cost_of_sales", "operating_income"],
                    sections=["financial_statement", "management_discussion"],
                    rules=_COMPARE,
                ),
                _ch(
                    "profit",
                    "利润分析",
                    hints=["利润"],
                    metrics=["gross_profit", "operating_income", "net_income"],
                    sections=["financial_statement"],
                    rules=_COMPARE,
                ),
                _ch(
                    "cash_flow",
                    "现金流",
                    hints=["现金"],
                    metrics=["net_cash_from_operating_activities"],
                    sections=["financial_statement"],
                    rules=_COMPARE,
                ),
                _ch("business_change", "重点业务变化", hints=["业务", "产品"], sections=["management_discussion"]),
                _ch("drivers", "经营驱动因素", hints=["驱动", "管理", "讨论"], sections=["management_discussion"], rules=["查找管理层解释"]),
                _ch("risks", "风险", hints=["风险"], sections=["risk_section"]),
                _ch("next_year", "下一年度关注点", hints=["结论", "建议"], must_cite=False),
            ],
        ),
        ReportTemplate(
            template_id="profitability",
            name="盈利能力分析报告",
            category="盈利分析",
            scenario="重点研究为什么赚钱、利润为什么变化",
            description="聚焦利润及驱动因素",
            chapters=[
                _ch("overview", "盈利概览", hints=["摘要", "盈利"], metrics=["net_income", "revenue"], must_cite=False),
                _ch("revenue", "营收变化", hints=["营收", "收入"], metrics=["revenue"], sections=["financial_statement", "management_discussion"], rules=_COMPARE),
                _ch(
                    "gross_margin",
                    "毛利率分析",
                    hints=["毛利"],
                    metrics=["revenue", "cost_of_sales", "gross_profit"],
                    sections=["management_discussion", "financial_statement"],
                    rules=_COMPARE,
                ),
                _ch("opex", "期间费用", hints=["费用"], metrics=["operating_income"], sections=["financial_statement", "management_discussion"], rules=_COMPARE),
                _ch("op_profit", "营业利润", hints=["营业利润"], metrics=["operating_income"], sections=["financial_statement"], rules=_COMPARE),
                _ch("net_profit", "净利润", hints=["净利润", "利润"], metrics=["net_income"], sections=["financial_statement"], rules=_COMPARE),
                _ch("returns", "ROE/ROA", hints=["ROE", "ROA", "净资产"], metrics=["net_income", "total_equity", "total_assets"], sections=["financial_statement"]),
                _ch("drivers", "利润增长驱动", hints=["驱动", "增长"], sections=["management_discussion"], rules=["查找管理层解释"]),
                _ch("quality", "盈利质量", hints=["现金", "质量"], metrics=["net_income", "net_cash_from_operating_activities"], sections=["financial_statement"]),
                _ch("sustainability", "可持续性判断", hints=["结论"], must_cite=False),
            ],
        ),
        ReportTemplate(
            template_id="cash_and_solvency",
            name="现金流与偿债能力报告",
            category="现金流与偿债",
            scenario="信贷、风险、债务分析",
            description="现金质量及债务分析",
            chapters=[
                _ch("overview", "现金流概览", hints=["现金", "摘要"], metrics=["net_cash_from_operating_activities"], must_cite=False),
                _ch("cfo", "经营现金流", hints=["经营现金"], metrics=["net_cash_from_operating_activities"], sections=["financial_statement"], rules=_COMPARE),
                _ch("cfi", "投资现金流", hints=["投资现金"], sections=["financial_statement"]),
                _ch("cff", "筹资现金流", hints=["筹资现金"], sections=["financial_statement"]),
                _ch("match", "现金流与利润匹配", hints=["匹配", "质量"], metrics=["net_income", "net_cash_from_operating_activities"], sections=["financial_statement"]),
                _ch("debt", "债务结构", hints=["负债", "债务"], metrics=["total_liabilities", "total_equity"], sections=["financial_statement"]),
                _ch("st_solvency", "短期偿债", hints=["流动", "短期"], metrics=["total_assets", "total_liabilities"], sections=["financial_statement"]),
                _ch("lt_solvency", "长期偿债", hints=["长期", "偿债"], metrics=["total_liabilities", "total_equity"], sections=["financial_statement"]),
                _ch("liquidity", "流动性风险", hints=["流动", "风险"], sections=["risk_section"]),
                _ch("conclusion", "结论", hints=["结论"], must_cite=False),
            ],
        ),
        ReportTemplate(
            template_id="financial_risk",
            name="财务风险评估报告",
            category="财务风险",
            scenario="风控、审查、企业风险分析",
            description="财务风险识别",
            chapters=[
                _ch("summary", "风险摘要", hints=["摘要", "风险"], sections=["risk_section"], must_cite=False),
                _ch("structure", "财务结构", hints=["结构", "资产", "负债"], metrics=["total_assets", "total_liabilities", "total_equity"], sections=["financial_statement"]),
                _ch("profit_risk", "盈利风险", hints=["盈利", "利润"], metrics=["net_income", "operating_income"], sections=["financial_statement", "risk_section"]),
                _ch("cash_risk", "现金流风险", hints=["现金"], metrics=["net_cash_from_operating_activities"], sections=["financial_statement", "risk_section"]),
                _ch("solvency_risk", "偿债风险", hints=["偿债", "负债"], metrics=["total_liabilities"], sections=["financial_statement", "risk_section"]),
                _ch("working_cap", "应收/存货风险", hints=["应收", "存货"], sections=["notes", "risk_section"]),
                _ch("capital", "资本结构", hints=["资本", "权益"], metrics=["total_equity", "total_liabilities"], sections=["financial_statement"]),
                _ch("anomalies", "异常指标", hints=["异常"], sections=["financial_statement", "management_discussion"]),
                _ch("rating", "风险等级", hints=["等级", "风险"], sections=["risk_section"]),
                _ch("actions", "风险事项与建议", hints=["建议", "结论"], must_cite=False),
            ],
        ),
        ReportTemplate(
            template_id="period_comparison",
            name="跨期财务对比报告",
            category="跨期对比",
            scenario="多年报比较（如 2022/2023/2024）",
            description="多年度趋势分析",
            chapters=[
                _ch("summary", "对比摘要", hints=["摘要", "对比"], must_cite=False),
                _ch("core_trend", "核心指标趋势", hints=["指标", "趋势"], metrics=["revenue", "net_income"], sections=["financial_statement"], rules=["列出多期数值与同比"]),
                _ch("revenue", "收入变化", hints=["收入", "营收"], metrics=["revenue"], sections=["financial_statement", "management_discussion"], rules=_COMPARE),
                _ch("profit", "利润变化", hints=["利润"], metrics=["net_income", "operating_income"], sections=["financial_statement"], rules=_COMPARE),
                _ch("margin", "毛利率变化", hints=["毛利"], metrics=["gross_profit", "revenue"], sections=["financial_statement"], rules=_COMPARE),
                _ch("opex", "费用率变化", hints=["费用"], metrics=["operating_income"], sections=["financial_statement"], rules=_COMPARE),
                _ch("cash", "现金流变化", hints=["现金"], metrics=["net_cash_from_operating_activities"], sections=["financial_statement"], rules=_COMPARE),
                _ch("balance", "资产负债结构", hints=["资产", "负债"], metrics=["total_assets", "total_liabilities"], sections=["financial_statement"]),
                _ch("reasons", "重大变动原因", hints=["驱动", "管理", "讨论"], sections=["management_discussion"], rules=["查找管理层解释"]),
                _ch("judgment", "趋势判断", hints=["结论", "趋势"], must_cite=False),
            ],
        ),
    ]


def get_report_template(template_id: str) -> ReportTemplate:
    for item in list_report_templates():
        if item.template_id == template_id:
            return item
    raise KeyError(template_id)
