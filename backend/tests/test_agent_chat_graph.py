"""Minimal unit tests for agent-chat messages graph helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from app.workflows.agent_chat.graph import (
    _format_answer,
    _invoke_chat_specialist,
    _latest_human_text,
    _prefer_primary_metrics,
    _preview_from_evidence,
    research_turn,
    standalone_research_question,
)
from app.workflows.orchestrator.graph import classify_intent
from src.claude_copilot.schemas.knowledge_graph import (
    GraphPath,
    KnowledgeGraphNode,
    KnowledgeGraphRelationship,
)
from src.claude_copilot.schemas.research import (
    ChatResearchResult,
    GroundedCitation,
    GroundedSynthesis,
    ResearchHit,
    ResearchPreviewResponse,
)


def test_latest_human_text_reads_last_user_message() -> None:
    messages = [
        HumanMessage(content="first"),
        AIMessage(content="reply"),
        HumanMessage(content="2021年营业收入是多少？"),
    ]
    assert _latest_human_text(messages) == "2021年营业收入是多少？"


def test_standalone_research_question_rewrites_follow_up() -> None:
    messages = [
        HumanMessage(content="2021年营业收入是多少？"),
        AIMessage(content="2021年营业收入为 9.3 亿。"),
        HumanMessage(content="净利润呢？"),
    ]
    assert standalone_research_question(messages) == ("2021年营业收入是多少？\n净利润呢？")


def test_standalone_research_question_keeps_complete_first_turn() -> None:
    messages = [HumanMessage(content="2021年营业收入是多少？")]
    assert standalone_research_question(messages) == "2021年营业收入是多少？"


def test_preview_from_evidence_exposes_graph_citations() -> None:
    preview = _preview_from_evidence(
        doc_id="doc-1",
        question="公司有哪些风险？",
        answer="存在市场风险 [G1]。",
        graph_paths=[
            GraphPath(
                path_id="rel:has_risk",
                summary="ACME -[HAS_RISK]-> market_risk",
                score=0.9,
                nodes=[
                    KnowledgeGraphNode(node_id="c", node_type="company", name="ACME"),
                    KnowledgeGraphNode(node_id="r", node_type="risk", name="market_risk"),
                ],
                relationships=[
                    KnowledgeGraphRelationship(
                        relationship_id="rel:has_risk",
                        relationship_type="HAS_RISK",
                        source_node_id="c",
                        target_node_id="r",
                        document_id="doc-1",
                    )
                ],
            )
        ],
    )
    assert preview.grounded is True
    assert preview.synthesis is not None
    assert preview.synthesis.citations[0].evidence_id == "G1"


def test_prefer_primary_metrics_keeps_larger_value() -> None:
    rows = [
        ("revenue", "2021", 4.35),
        ("revenue", "2021", 469378042.95),
    ]
    preferred = _prefer_primary_metrics(rows)
    assert preferred == [("revenue", "2021", 469378042.95)]


def test_format_answer_prefers_primary_when_llm_fails() -> None:
    class _Preview:
        answer = "revenue(2021)=4.35；revenue(2021)=469378042.95"
        synthesis = None
        metrics = [
            {"metric_key": "revenue", "period": "2021", "value": 4.35},
            {"metric_key": "revenue", "period": "2021", "value": 469378042.95},
        ]
        warnings = [
            "grounded synthesis failed: Server error '502 Bad Gateway' for url 'http://192.168.0.102:30000/v1/chat/completions'"
        ]
        query_analysis = {"intent": "structured", "routes": ["sql"]}

    text = _format_answer(_Preview())
    assert "469378042.95" in text
    assert "4.35" not in text
    assert "本地 LLM 暂时不可用" in text


def test_format_answer_includes_fusion_summary() -> None:
    class _Fusion:
        query_intent = "hybrid"
        routes = ["vector", "sql"]
        summary = "意图=hybrid，启用通道：语义片段 + 结构化指标。"
        highlights = ["[结构化] revenue 2021 = 931944638"]

    class _Preview:
        answer = ""
        synthesis = None
        metrics = [{"metric_key": "revenue", "period": "2021", "value": 931944638}]
        warnings = ["grounded synthesis failed: HTTPStatusError 502"]
        query_analysis = {"intent": "hybrid", "routes": ["vector", "sql"]}
        fusion_summary = _Fusion()

    text = _format_answer(_Preview())
    assert "混合检索摘要" in text
    assert "931944638" in text
    assert "intent=hybrid" not in text
    assert "routes=" not in text


def test_format_answer_fusion_heading_follows_intent() -> None:
    class _Fusion:
        query_intent = "structured"
        routes = ["sql"]
        summary = "命中营收指标"
        highlights = []

    class _Preview:
        answer = "营收为 1。"
        synthesis = None
        metrics = []
        warnings = []
        query_analysis = None
        fusion_summary = _Fusion()

    text = _format_answer(_Preview())
    assert "结构化查询摘要" in text
    assert "混合检索摘要" not in text


def test_format_answer_humanizes_route_fallback_without_fusion() -> None:
    class _Preview:
        answer = "营收为 1。"
        synthesis = None
        metrics = []
        warnings = []
        query_analysis = {"intent": "hybrid", "routes": ["vector", "sql"]}
        fusion_summary = None

    text = _format_answer(_Preview())
    assert "检索通道：混合检索（语义 · 结构化）" in text
    assert "intent=" not in text
    assert "routes=" not in text


def test_classify_intent_routes_market_risk_question() -> None:
    assert classify_intent({"question": "公司面临哪些市场风险或风险暴露？"})["agent_used"] == "risk"
    assert classify_intent({"question": "2021年营业收入是多少？"})["agent_used"] == "structured"
    assert (
        classify_intent({"question": "2021年营业收入相对2020年为什么增长？"})["agent_used"]
        == "quant"
    )
    assert classify_intent({"question": "对比两家公司的营业收入"})["agent_used"] == "compare"
    assert classify_intent({"question": "生成提纲报告"})["agent_used"] == "report"


def test_research_turn_runs_secondary_specialist_for_multi_intent() -> None:
    class _Record:
        class metadata:
            company = "指南针"

    calls: list[str] = []

    def fake_invoke(*, agent_used: str, question: str, **_kwargs: Any) -> str:
        calls.append(agent_used)
        return f"{agent_used}-block for {question[:8]}"

    with (
        patch(
            "app.workflows.agent_chat.graph._resolve_doc_id",
            return_value="doc-1",
        ),
        patch(
            "app.workflows.agent_chat.graph._resolve_doc_id_b",
            return_value=None,
        ),
        patch("app.api.dependencies.get_document_pipeline_service") as get_pipeline,
        patch(
            "app.workflows.agent_chat.graph._invoke_chat_specialist",
            side_effect=fake_invoke,
        ),
    ):
        get_pipeline.return_value.get_document.return_value = _Record()
        result = research_turn(
            {"messages": [HumanMessage(content="2021年营业收入是多少以及有哪些市场风险？")]},
            {},
        )

    assert calls == ["risk", "structured"]
    text = str(result["messages"][0].content)
    assert "risk-block" in text
    assert "次级 · 结构化指标" in text
    assert "次级 · structured" not in text
    assert "多意图" in text
    assert "已附带执行次级" in text


def test_research_turn_empty_question_avoids_serving_jargon() -> None:
    result = research_turn({"messages": [HumanMessage(content="   ")]}, {})
    text = str(result["messages"][0].content)
    assert "请输入要研究的问题" in text
    assert "研究财报" in text
    assert "Serving" not in text


def test_research_turn_without_doc_id_points_to_picker() -> None:
    with patch("app.workflows.agent_chat.graph._resolve_doc_id", return_value=None):
        result = research_turn(
            {"messages": [HumanMessage(content="2021年营业收入是多少？")]},
            {},
        )

    text = str(result["messages"][0].content)
    assert "未选择研究文档" in text
    assert "研究财报" in text
    assert "AGENT_CHAT_DOC_ID" not in text
    assert "configurable" not in text
    assert "Serving" not in text


def test_compare_without_doc_id_b_warns_and_skips_workflow() -> None:
    """Missing second doc must be an explicit warning — never invent company B."""
    with patch("app.workflows.comparison_workflow.graph.graph.invoke") as compare_invoke:
        answer = _invoke_chat_specialist(
            agent_used="compare",
            question="对比两家公司的营业收入",
            doc_id="doc-a",
            doc_id_b=None,
            company_id=None,
        )

    compare_invoke.assert_not_called()
    assert isinstance(answer, ResearchPreviewResponse)
    text = answer.answer
    assert "【对比】" in text
    assert "Comparator" not in text
    assert "未选择第二份文档" in text
    assert "对比财报" in text
    assert "AGENT_CHAT_DOC_ID_B" not in text
    assert "doc_id_b" not in text
    assert "configurable" not in text
    # No fabricated peer metrics / company names.
    assert "营业收入" not in text or "未配置" in text
    assert "931944638" not in text
    assert "差额" not in text
    assert answer.metrics == []
    assert answer.grounded is False
    assert answer.warnings
    assert "对比财报" in answer.warnings[0]
    assert "doc_id_b" not in answer.warnings[0]


def test_research_snapshot_survives_serialization_and_stays_with_its_turn() -> None:
    from types import SimpleNamespace

    from langchain_core.messages import messages_from_dict, messages_to_dict

    previews = [
        ResearchPreviewResponse(
            doc_id=doc_id,
            question="营收是多少？",
            answer=f"{value}元 [V1]",
            hits=[
                ResearchHit(
                    segment_id=f"{doc_id}-segment",
                    score=0.9,
                    content=f"营收{value}元",
                    metadata={"page_start": page},
                )
            ],
            synthesis=GroundedSynthesis(
                answer=f"{value}元 [V1]",
                confidence=1,
                citations=[GroundedCitation(evidence_id="V1", claim=f"营收{value}元")],
            ),
            grounded=True,
        )
        for doc_id, value, page in [("doc-a", 100, 3), ("doc-b", 200, 8)]
    ]
    history = []
    with (
        patch("app.api.dependencies.get_document_pipeline_service") as pipeline,
        patch("app.api.dependencies.get_research_service") as research,
    ):
        pipeline.return_value.get_document.return_value = SimpleNamespace(
            metadata=SimpleNamespace(company="测试公司")
        )
        research.return_value.preview.side_effect = previews
        for index, preview in enumerate(previews):
            history.append(HumanMessage(id=f"human-{index}", content=preview.question))
            out = research_turn(
                {"messages": history, "doc_id": preview.doc_id},
                {"configurable": {"thread_id": "thread-a"}},
            )
            history.extend(out["messages"])
    restored = messages_from_dict(messages_to_dict(history))
    for index, preview in enumerate(previews):
        message = restored[index * 2 + 1]
        snapshot = ChatResearchResult.model_validate(message.additional_kwargs["research_result"])
        assert snapshot.thread_id == "thread-a"
        assert snapshot.request_message_id == f"human-{index}"
        assert snapshot.previews == [preview]
        assert message.id
        assert preview.answer in message.content
    assert restored[1].id != restored[3].id


def test_secondary_research_keeps_its_evidence_without_rerunning() -> None:
    from types import SimpleNamespace

    preview = ResearchPreviewResponse(
        doc_id="doc-a", question="营收和风险", answer="100元", warnings=["证据有限"]
    )
    with (
        patch("app.api.dependencies.get_document_pipeline_service") as pipeline,
        patch(
            "app.workflows.agent_chat.graph._invoke_chat_specialist",
            side_effect=["风险摘要", preview],
        ) as invoke,
        patch(
            "app.workflows.orchestrator.graph.classify_intent",
            return_value={
                "agent_used": "risk",
                "secondary_intent": "structured",
                "sub_intents": ["risk", "structured"],
            },
        ),
    ):
        pipeline.return_value.get_document.return_value = SimpleNamespace(
            metadata=SimpleNamespace(company="测试")
        )
        out = research_turn(
            {"doc_id": "doc-a", "messages": [HumanMessage(id="human-1", content="营收和风险")]},
            {"configurable": {"thread_id": "thread-b"}},
        )
    assert invoke.call_count == 2
    snapshot = ChatResearchResult.model_validate(
        out["messages"][0].additional_kwargs["research_result"]
    )
    assert snapshot.previews == [preview]
    assert snapshot.thread_id == "thread-b"


def test_risk_quant_compare_report_snapshots_carry_this_turn_evidence() -> None:
    risk_state = {
        "hits": [
            {
                "segment_id": "seg-risk",
                "score": 0.8,
                "content": "市场风险包括汇率波动",
                "metadata": {"page_start": 12},
            }
        ],
        "risk_findings": [{"risk_type": "market_risk", "summary": "汇率", "evidence": "汇率波动"}],
        "warnings": [],
        "answer": "识别到 1 条风险",
    }
    quant_state = {
        "metrics": [
            {
                "company_id": "c1",
                "company": "测试",
                "document_id": "doc-a",
                "metric_key": "revenue",
                "period": "2021",
                "value": 100,
            }
        ],
        "calculations": [
            {
                "metric_key": "revenue",
                "yearly_values": {2020: 90, 2021: 100},
                "yoy_growth": {2021: 0.111},
                "cagr": 0.111,
            }
        ],
        "warnings": [],
        "answer": "revenue 2021=100",
    }
    compare_state = {
        "compare_matrix": [
            {"metric_key": "revenue", "period": "2021", "value_a": 100, "value_b": 80}
        ],
        "compare_highlights": ["revenue 2021：A 高于 B"],
        "warnings": [],
        "answer": "A=100 B=80",
    }
    report_state = {
        "report_sections": [{"title": "经营概述", "bullets": ["营收上升"]}],
        "calculations": [{"metric_key": "revenue", "yearly_values": {2021: 100}}],
        "warnings": [],
        "answer": "提纲正文",
    }

    with (
        patch("app.workflows.risk.graph.graph.invoke", return_value=risk_state),
        patch("app.workflows.quant.graph.graph.invoke", return_value=quant_state),
        patch(
            "app.workflows.comparison_workflow.graph.graph.invoke",
            return_value=compare_state,
        ),
        patch("app.workflows.report_workflow.graph.graph.invoke", return_value=report_state),
    ):
        risk = _invoke_chat_specialist(
            agent_used="risk", question="有哪些风险", doc_id="doc-a", doc_id_b=None, company_id="c1"
        )
        quant = _invoke_chat_specialist(
            agent_used="quant", question="同比增长", doc_id="doc-a", doc_id_b=None, company_id="c1"
        )
        compare = _invoke_chat_specialist(
            agent_used="compare",
            question="对比营收",
            doc_id="doc-a",
            doc_id_b="doc-b",
            company_id="c1",
        )
        report = _invoke_chat_specialist(
            agent_used="report",
            question="写一份报告",
            doc_id="doc-a",
            doc_id_b=None,
            company_id="c1",
        )

    assert isinstance(risk, ResearchPreviewResponse)
    assert "【风险】" in risk.answer
    assert "Risk Agent" not in risk.answer
    assert risk.grounded is True
    assert risk.hits[0].segment_id == "seg-risk"
    assert risk.synthesis is not None
    assert any(item.evidence_id == "V1" for item in risk.synthesis.citations)
    assert risk.fusion_summary is not None
    assert "汇率" in risk.fusion_summary.summary

    assert "【量化】" in quant.answer
    assert "Quant Agent" not in quant.answer
    assert quant.grounded is True
    assert quant.metrics[0].value == 100
    assert any(
        item.evidence_id == "S1" for item in (quant.synthesis.citations if quant.synthesis else [])
    )
    assert quant.fusion_summary is not None
    assert "量化要点" in quant.fusion_summary.summary
    assert "revenue" in quant.fusion_summary.summary

    assert {item.document_id for item in compare.metrics} == {"doc-a", "doc-b"}
    assert compare.grounded is True
    assert "[S1]" in compare.answer
    assert "[S2]" in compare.answer
    assert compare.fusion_summary is not None
    assert "A 高于 B" in compare.fusion_summary.summary

    assert report.hits[0].metadata["section_title"] == "经营概述"
    assert report.metrics[0].value == 100
    assert report.grounded is True
    assert "[V1]" in report.answer
    assert "[S1]" in report.answer
    assert report.fusion_summary is not None
    assert "经营概述" in report.fusion_summary.summary
