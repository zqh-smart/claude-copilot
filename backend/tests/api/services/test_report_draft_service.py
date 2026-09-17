from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.api.services.report_draft_service import ReportDraftService, ReportDraftStore
from src.claude_copilot.schemas.report_studio import (
    CreateReportDraftRequest,
    PatchReportDraftRequest,
)
from src.claude_copilot.schemas.workflows import ReportOutlineResponse


class _FakeWorkflow:
    def report_outline(self, request):  # noqa: ANN001
        return ReportOutlineResponse(
            answer_markdown="# 提纲",
            sections=[
                {"title": "核心财务指标", "bullets": ["营业收入 100 亿元"]},
                {"title": "风险提示", "bullets": ["原材料价格波动"]},
                {"title": "公司与文档", "bullets": ["文档 ID：doc-1"]},
            ],
            hits=[
                {
                    "content": "管理层讨论：主营收入增长来自核心产品。",
                    "metadata": {
                        "section_title": "管理层讨论与分析",
                        "section_type": "management_discussion",
                        "page": 42,
                    },
                }
            ],
            warnings=["本报告为提纲 MVP，非正式投研报告。", "缺少 2022 年可比数据"],
        )


class _FakePipeline:
    def get_document(self, doc_id: str):
        return SimpleNamespace(
            doc_id=doc_id,
            filename="特斯拉2023年报.pdf",
            metadata=SimpleNamespace(
                company="特斯拉",
                year=2023,
                doc_type="年报",
            ),
        )


def _service(tmp_path: Path) -> ReportDraftService:
    return ReportDraftService(
        workflow_service=_FakeWorkflow(),
        document_pipeline_service=_FakePipeline(),
        store=ReportDraftStore(tmp_path / "studio_drafts"),
    )


def test_create_draft_maps_template_chapters_and_citations(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        CreateReportDraftRequest(
            doc_ids=["doc-1"],
            template_id="comprehensive_financial",
            prompt="重点看财务与风险",
        )
    )
    titles = [section.title for section in draft.sections]
    assert "执行摘要" in titles
    assert "核心财务指标" in titles
    assert "财务异常与风险" in titles
    financial = next(section for section in draft.sections if section.chapter_id == "core_metrics")
    assert "营业收入" in financial.content or "分析要求" in financial.content
    assert financial.citation_ids
    assert draft.citations
    assert any("p.42" in item.path_label for item in draft.citations)
    assert draft.citations[0].path_label.startswith("特斯拉2023年报.pdf")
    assert all("提纲 MVP" not in warning for warning in draft.warnings)
    assert any("缺少 2022" in warning for warning in draft.warnings)


def test_assist_brief_then_apply(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        CreateReportDraftRequest(doc_ids=["doc-1"], template_id="financial_risk")
    )
    section = draft.sections[0]
    preview = service.assist(
        draft.draft_id,
        section_id=section.section_id,
        instruction="精简本章",
        apply=False,
    )
    assert preview.applied is False
    assert preview.draft is None
    applied = service.assist(
        draft.draft_id,
        section_id=section.section_id,
        instruction="精简本章",
        apply=True,
    )
    assert applied.applied is True
    assert applied.draft is not None
    assert applied.draft.status == "revised"


def test_patch_section_content(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        CreateReportDraftRequest(doc_ids=["doc-1"], template_id="period_comparison")
    )
    section = draft.sections[0].model_copy(update={"content": "人工改写后的行业概览 [C1]"})
    updated = service.patch_draft(
        draft.draft_id,
        PatchReportDraftRequest(sections=[section, *draft.sections[1:]]),
    )
    assert updated.sections[0].content.startswith("人工改写")
    assert updated.status == "revised"


def test_store_reads_legacy_template_ids(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        CreateReportDraftRequest(doc_ids=["doc-1"], template_id="comprehensive_financial")
    )
    path = tmp_path / "studio_drafts" / f"{draft.draft_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["template_id"] = "investment"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = service.get_draft(draft.draft_id)
    summaries = service.list_drafts()

    assert loaded.template_id == "comprehensive_financial"
    assert summaries[0].template_id == "comprehensive_financial"
