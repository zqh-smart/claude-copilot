"""Render report-workflow output into downloadable HTML and PDF artifacts."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from app.api.services.formal_report_composer import ReportSource, compose_formal_report
from app.api.services.workflow_api_service import WorkflowApiService
from src.claude_copilot.schemas.workflows import (
    ReportBundleExportRequest,
    ReportExportRequest,
    ReportOutlineRequest,
)


@dataclass(frozen=True)
class ReportArtifact:
    content: bytes
    media_type: str
    filename: str


class ReportArtifactService:
    def __init__(self, workflow_service: WorkflowApiService) -> None:
        self._workflow_service = workflow_service

    def export(self, request: ReportExportRequest) -> ReportArtifact:
        outline = self._workflow_service.report_outline(
            ReportOutlineRequest(
                doc_id=request.doc_id,
                question=request.question,
                top_k=request.top_k,
                use_workflow=request.use_workflow,
            )
        )
        safe_stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", request.title).strip("-")
        safe_stem = safe_stem or "financial-report"
        if request.format == "html":
            content = self._render_html(
                title=request.title,
                markdown=outline.answer_markdown,
                warnings=outline.warnings,
            )
            return ReportArtifact(
                content=content.encode("utf-8"),
                media_type="text/html; charset=utf-8",
                filename=f"{safe_stem}.html",
            )
        return ReportArtifact(
            content=self._render_pdf(
                title=request.title,
                markdown=outline.answer_markdown,
                warnings=outline.warnings,
            ),
            media_type="application/pdf",
            filename=f"{safe_stem}.pdf",
        )

    def export_bundle(self, request: ReportBundleExportRequest) -> ReportArtifact:
        question = request.question.strip()
        if not question:
            question = (
                "生成财务表现、增长趋势、业务与风险的投资研究报告"
                if request.report_type == "investment"
                else "生成风险识别、风险证据、影响与缓释建议的风险报告"
            )
        sources: list[ReportSource] = []
        for doc_id in dict.fromkeys(request.doc_ids):
            outline = self._workflow_service.report_outline(
                ReportOutlineRequest(
                    doc_id=doc_id,
                    question=question,
                    top_k=request.top_k,
                    use_workflow=True,
                )
            )
            sources.append(ReportSource(doc_id=doc_id, outline=outline))
        report = compose_formal_report(
            report_type=request.report_type,
            question=question,
            sources=sources,
        )
        safe_stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", request.title).strip("-")
        safe_stem = safe_stem or "financial-report"
        if request.format == "html":
            content = self._render_html(
                title=request.title,
                markdown=report.markdown,
                warnings=report.warnings,
            )
            return ReportArtifact(
                content=content.encode("utf-8"),
                media_type="text/html; charset=utf-8",
                filename=f"{safe_stem}.html",
            )
        return ReportArtifact(
            content=self._render_pdf(
                title=request.title,
                markdown=report.markdown,
                warnings=report.warnings,
            ),
            media_type="application/pdf",
            filename=f"{safe_stem}.pdf",
        )

    def _render_html(self, *, title: str, markdown: str, warnings: list[str]) -> str:
        body_parts: list[str] = []
        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            escaped = html.escape(line.lstrip("#- "))
            if line.startswith("### "):
                body_parts.append(f"<h3>{escaped}</h3>")
            elif line.startswith("## "):
                body_parts.append(f"<h2>{escaped}</h2>")
            elif line.startswith("# "):
                body_parts.append(f"<h1>{escaped}</h1>")
            elif line.startswith(("- ", "* ")):
                body_parts.append(f'<p class="bullet">• {escaped}</p>')
            else:
                body_parts.append(f"<p>{html.escape(line)}</p>")
        warning_html = "".join(f"<li>{html.escape(item)}</li>" for item in warnings)
        warning_section = ""
        if warnings:
            warning_section = (
                f'<section class="warnings"><h2>限制与提示</h2><ul>{warning_html}</ul></section>'
            )
        return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font-family:"Microsoft YaHei",sans-serif;max-width:900px;margin:40px auto;
padding:0 28px;color:#1c241c;line-height:1.7}}
h1,h2,h3{{color:#1f5c45}} h1{{border-bottom:2px solid #1f5c45;padding-bottom:12px}}
.meta{{color:#5a6458}} .warnings{{background:#f3e2cf;padding:14px 20px;border-radius:10px}}
.bullet{{padding-left:16px}}
</style></head><body><h1>{html.escape(title)}</h1><p class="meta">Claude Copilot 自动生成</p>
{"".join(body_parts)}
{warning_section}
</body></html>"""

    def _render_pdf(self, *, title: str, markdown: str, warnings: list[str]) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        font_name = "Helvetica"
        for font_path in (Path("C:/Windows/Fonts/simhei.ttf"), Path("C:/Windows/Fonts/simsun.ttc")):
            if font_path.exists():
                font_name = "ClaudeCopilotCJK"
                if font_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                break

        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=22 * mm,
            leftMargin=22 * mm,
            topMargin=22 * mm,
            bottomMargin=20 * mm,
            title=title,
            author="Claude Copilot",
        )
        base = getSampleStyleSheet()
        styles = {
            "title": ParagraphStyle(
                "CCTitle",
                parent=base["Title"],
                fontName=font_name,
                fontSize=22,
                leading=30,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#1f5c45"),
                spaceAfter=18,
            ),
            "h1": ParagraphStyle(
                "CCH1", parent=base["Heading1"], fontName=font_name, fontSize=16, leading=22
            ),
            "h2": ParagraphStyle(
                "CCH2", parent=base["Heading2"], fontName=font_name, fontSize=13, leading=19
            ),
            "body": ParagraphStyle(
                "CCBody", parent=base["BodyText"], fontName=font_name, fontSize=10.5, leading=17
            ),
            "warning": ParagraphStyle(
                "CCWarning",
                parent=base["BodyText"],
                fontName=font_name,
                fontSize=9.5,
                leading=15,
                textColor=colors.HexColor("#8a4b12"),
            ),
        }
        story = [Paragraph(html.escape(title), styles["title"]), Spacer(1, 4 * mm)]
        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                story.append(Spacer(1, 2 * mm))
                continue
            text = html.escape(line.lstrip("#- "))
            if line.startswith("# "):
                story.append(Paragraph(text, styles["h1"]))
            elif line.startswith(("## ", "### ")):
                story.append(Paragraph(text, styles["h2"]))
            elif line.startswith(("- ", "* ")):
                story.append(Paragraph(f"- {text}", styles["body"]))
            else:
                story.append(Paragraph(html.escape(line), styles["body"]))
        if warnings:
            story.extend((Spacer(1, 4 * mm), Paragraph("限制与提示", styles["h2"])))
            story.extend(
                Paragraph(f"- {html.escape(item)}", styles["warning"]) for item in warnings
            )

        def add_page_number(canvas, doc) -> None:
            canvas.saveState()
            canvas.setFont(font_name, 8)
            canvas.setFillColor(colors.HexColor("#5a6458"))
            canvas.drawRightString(A4[0] - 22 * mm, 10 * mm, str(doc.page))
            canvas.restoreState()

        document.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
        return buffer.getvalue()


def get_report_artifact_service() -> ReportArtifactService:
    from app.api.services.workflow_api_service import get_workflow_api_service

    return ReportArtifactService(get_workflow_api_service())
