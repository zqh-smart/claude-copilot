"""Report studio APIs: templates, drafts, assist, export."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.services.report_artifact_service import (
    ReportArtifactService,
    get_report_artifact_service,
)
from app.api.services.report_draft_service import ReportDraftService, get_report_draft_service
from app.api.services.report_template_catalog import list_report_templates as catalog_templates
from app.core.errors import DocumentNotFoundError
from src.claude_copilot.schemas.report_studio import (
    AssistReportDraftRequest,
    AssistReportDraftResponse,
    CreateReportDraftRequest,
    ExportReportDraftRequest,
    PatchReportDraftRequest,
    ReportDraft,
    ReportDraftSummary,
    ReportStudioCatalog,
    ReportTemplate,
)

router = APIRouter(tags=["report-studio"])


def _attachment_header(filename: str) -> str:
    safe = filename.replace('"', "").replace("\r", "").replace("\n", "")
    encoded = quote(safe, safe="")
    return f"attachment; filename=report; filename*=UTF-8''{encoded}"


@router.get("/api/v1/report/templates", response_model=list[ReportTemplate])
def list_report_templates() -> list[ReportTemplate]:
    return catalog_templates()


@router.get("/api/v1/report/studio/catalog", response_model=ReportStudioCatalog)
def report_studio_catalog() -> ReportStudioCatalog:
    return ReportStudioCatalog(templates=catalog_templates())


@router.get("/api/v1/report/drafts", response_model=list[ReportDraftSummary])
def list_report_drafts(
    service: Annotated[ReportDraftService, Depends(get_report_draft_service)],
) -> list[ReportDraftSummary]:
    return service.list_drafts()


@router.post("/api/v1/report/drafts", response_model=ReportDraft)
def create_report_draft(
    request: CreateReportDraftRequest,
    service: Annotated[ReportDraftService, Depends(get_report_draft_service)],
) -> ReportDraft:
    try:
        return service.create_draft(request)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown template: {exc}") from exc


@router.get("/api/v1/report/drafts/{draft_id}", response_model=ReportDraft)
def get_report_draft(
    draft_id: str,
    service: Annotated[ReportDraftService, Depends(get_report_draft_service)],
) -> ReportDraft:
    try:
        return service.get_draft(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Draft not found") from exc


@router.patch("/api/v1/report/drafts/{draft_id}", response_model=ReportDraft)
def patch_report_draft(
    draft_id: str,
    request: PatchReportDraftRequest,
    service: Annotated[ReportDraftService, Depends(get_report_draft_service)],
) -> ReportDraft:
    try:
        return service.patch_draft(draft_id, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Draft not found") from exc


@router.post(
    "/api/v1/report/drafts/{draft_id}/assist",
    response_model=AssistReportDraftResponse,
)
def assist_report_draft(
    draft_id: str,
    request: AssistReportDraftRequest,
    service: Annotated[ReportDraftService, Depends(get_report_draft_service)],
) -> AssistReportDraftResponse:
    try:
        return service.assist(
            draft_id,
            section_id=request.section_id,
            instruction=request.instruction,
            apply=request.apply,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Draft not found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Section not found: {exc}") from exc


@router.post("/api/v1/report/drafts/{draft_id}/export")
def export_report_draft(
    draft_id: str,
    request: ExportReportDraftRequest,
    drafts: Annotated[ReportDraftService, Depends(get_report_draft_service)],
    artifacts: Annotated[ReportArtifactService, Depends(get_report_artifact_service)],
) -> Response:
    try:
        draft = drafts.get_draft(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Draft not found") from exc
    title = request.title or draft.title
    markdown = drafts.draft_markdown(draft)
    if request.format == "html":
        content = artifacts._render_html(
            title=title,
            markdown=markdown,
            warnings=draft.warnings,
        ).encode("utf-8")
        media = "text/html; charset=utf-8"
        filename = f"{title}.html"
    else:
        content = artifacts._render_pdf(
            title=title,
            markdown=markdown,
            warnings=draft.warnings,
        )
        media = "application/pdf"
        filename = f"{title}.pdf"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": _attachment_header(filename)},
    )
