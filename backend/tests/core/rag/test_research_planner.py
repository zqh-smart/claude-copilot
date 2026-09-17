from app.core.rag.research_planner import is_deep_research_question, plan_deep_research


def test_is_deep_research_question_report_cue() -> None:
    assert is_deep_research_question("请写一份深度分析报告，评估投资价值")


def test_is_deep_research_question_multi_axis() -> None:
    q = "请分析该公司营收、利润、现金流与主要风险在近三年的变化趋势"
    assert is_deep_research_question(q)


def test_plan_deep_research_includes_core_subtasks() -> None:
    tasks = plan_deep_research("生成全面分析报告")
    task_ids = {task.task_id for task in tasks}
    assert {"revenue_trend", "profitability", "cash_quality", "risks"} <= task_ids
