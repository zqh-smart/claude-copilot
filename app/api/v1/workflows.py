"""P7c thin Compare / Report outline APIs (JSON + Markdown, no product UI)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.services.report_artifact_service import (
    ReportArtifactService,
    get_report_artifact_service,
)
from app.api.services.workflow_api_service import WorkflowApiService, get_workflow_api_service
from src.claude_copilot.schemas.workflows import (
    CompareRequest,
    CompareResponse,
    ReportBundleExportRequest,
    ReportExportRequest,
    ReportOutlineRequest,
    ReportOutlineResponse,
)

router = APIRouter(tags=["workflows-lite"])


@router.post("/api/v1/compare", response_model=CompareResponse)
def compare_documents(
    request: CompareRequest,
    service: Annotated[WorkflowApiService, Depends(get_workflow_api_service)],
) -> CompareResponse:
    """Dual-doc metric comparison. Returns Markdown + matrix JSON. No BI UI."""
    return service.compare(request)


@router.post("/api/v1/report/outline", response_model=ReportOutlineResponse)
def report_outline(
    request: ReportOutlineRequest,
    service: Annotated[WorkflowApiService, Depends(get_workflow_api_service)],
) -> ReportOutlineResponse:
    """Single-doc outline report. Returns Markdown (+ sections). No PDF/center."""
    return service.report_outline(request)


@router.post("/api/v1/report/export")
def export_report(
    request: ReportExportRequest,
    service: Annotated[ReportArtifactService, Depends(get_report_artifact_service)],
) -> Response:
    artifact = service.export(request)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )


@router.post("/api/v1/report/export-bundle")
def export_report_bundle(
    request: ReportBundleExportRequest,
    service: Annotated[ReportArtifactService, Depends(get_report_artifact_service)],
) -> Response:
    artifact = service.export_bundle(request)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )
