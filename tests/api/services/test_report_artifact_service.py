"""Tests for HTML/PDF report artifact rendering."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import pdfplumber
from pypdf import PdfReader

from app.api.services.report_artifact_service import ReportArtifactService
from src.claude_copilot.schemas.workflows import (
    ReportBundleExportRequest,
    ReportExportRequest,
    ReportOutlineResponse,
)


def _service() -> ReportArtifactService:
    workflow_service = MagicMock()
    workflow_service.report_outline.return_value = ReportOutlineResponse(
        answer_markdown="# 摘要\n## 财务指标\n- 营业收入增长 12%\n<script>alert(1)</script>",
        warnings=["数据仅覆盖已入库文档"],
    )
    return ReportArtifactService(workflow_service)


def test_html_export_escapes_untrusted_content() -> None:
    artifact = _service().export(
        ReportExportRequest(doc_id="doc-1", title="测试报告", format="html")
    )

    text = artifact.content.decode("utf-8")
    assert artifact.media_type == "text/html; charset=utf-8"
    assert artifact.filename == "测试报告.html"
    assert "<script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "营业收入增长 12%" in text
    assert "数据仅覆盖已入库文档" in text


def test_pdf_export_is_parseable_and_preserves_chinese_text() -> None:
    artifact = _service().export(
        ReportExportRequest(doc_id="doc-1", title="测试报告", format="pdf")
    )

    assert artifact.content.startswith(b"%PDF")
    assert artifact.filename == "测试报告.pdf"
    reader = PdfReader(BytesIO(artifact.content))
    assert len(reader.pages) >= 1
    assert reader.metadata is not None
    assert reader.metadata.title == "测试报告"
    with pdfplumber.open(BytesIO(artifact.content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "测试报告" in text
    assert "营业收入增长" in text
    assert "数据仅覆盖已入库文档" in text


def test_bundle_export_combines_multiple_documents_and_risk_prompt() -> None:
    workflow_service = MagicMock()
    workflow_service.report_outline.side_effect = [
        ReportOutlineResponse(answer_markdown="# 2022 年风险", warnings=["旧期数据"]),
        ReportOutlineResponse(answer_markdown="# 2023 年风险"),
    ]
    service = ReportArtifactService(workflow_service)

    artifact = service.export_bundle(
        ReportBundleExportRequest(
            doc_ids=["doc-2022", "doc-2023", "doc-2023"],
            report_type="risk",
            title="两年风险报告",
            format="html",
        )
    )

    text = artifact.content.decode("utf-8")
    assert text.count("来源文档") == 2
    assert "2022 年风险" in text
    assert "2023 年风险" in text
    assert "doc-2022: 旧期数据" in text
    assert workflow_service.report_outline.call_count == 2
    first_request = workflow_service.report_outline.call_args_list[0].args[0]
    assert "风险识别" in first_request.question
