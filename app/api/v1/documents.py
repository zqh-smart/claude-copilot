from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.api.dependencies import get_document_service, get_ingestion_job_service
from app.api.services import DocumentService, IngestionJobService
from app.core.errors import IngestionJobNotFoundError
from src.claude_copilot.schemas.document import DocumentRecord, DocumentSegment
from src.claude_copilot.schemas.ingestion import (
    IngestionBatchResponse,
    IngestionJob,
    IngestionQueueMetrics,
)
from src.claude_copilot.schemas.knowledge_graph import DocumentKnowledgeGraph

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _parse_aliases(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


@router.post("/upload", response_model=DocumentRecord)
async def upload_document(
    file: UploadFile = File(...),
    company: str | None = Form(default=None),
    year: int | None = Form(default=None),
    doc_type: str = Form(default="financial_report"),
    source: str = Form(default="upload"),
    industry: str | None = Form(default=None),
    company_aliases: str | None = Form(default=None),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentRecord:
    return await document_service.upload_document(
        file=file,
        company=company,
        year=year,
        doc_type=doc_type,
        source=source,
        industry=industry,
        company_aliases=_parse_aliases(company_aliases),
    )


@router.post(
    "/upload/async",
    response_model=IngestionJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document_async(
    file: UploadFile = File(...),
    company: str | None = Form(default=None),
    year: int | None = Form(default=None),
    doc_type: str = Form(default="financial_report"),
    source: str = Form(default="upload"),
    industry: str | None = Form(default=None),
    company_aliases: str | None = Form(default=None),
    max_attempts: int | None = Form(default=None, ge=1, le=10),
    job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> IngestionJob:
    return job_service.submit(
        filename=file.filename or "uploaded_document",
        content_type=file.content_type,
        content=await file.read(),
        company=company,
        year=year,
        doc_type=doc_type,
        source=source,
        industry=industry,
        company_aliases=_parse_aliases(company_aliases),
        max_attempts=max_attempts,
    )


@router.post(
    "/upload/batch/async",
    response_model=IngestionBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document_batch_async(
    files: list[UploadFile] = File(...),
    company: str | None = Form(default=None),
    year: int | None = Form(default=None),
    doc_type: str = Form(default="financial_report"),
    source: str = Form(default="upload"),
    industry: str | None = Form(default=None),
    company_aliases: str | None = Form(default=None),
    max_attempts: int | None = Form(default=None, ge=1, le=10),
    job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> IngestionBatchResponse:
    jobs = []
    for file in files:
        jobs.append(
            job_service.submit(
                filename=file.filename or "uploaded_document",
                content_type=file.content_type,
                content=await file.read(),
                company=company,
                year=year,
                doc_type=doc_type,
                source=source,
                industry=industry,
                company_aliases=_parse_aliases(company_aliases),
                max_attempts=max_attempts,
            )
        )
    return IngestionBatchResponse(jobs=jobs)


@router.get("/jobs", response_model=list[IngestionJob])
def list_ingestion_jobs(
    limit: int = Query(default=100, ge=1, le=1000),
    job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> list[IngestionJob]:
    return job_service.list_jobs(limit=limit)


@router.get("/jobs/metrics", response_model=IngestionQueueMetrics)
def get_ingestion_queue_metrics(
    job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> IngestionQueueMetrics:
    return job_service.get_metrics()


@router.get("/jobs/{job_id}", response_model=IngestionJob)
def get_ingestion_job(
    job_id: str,
    job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> IngestionJob:
    try:
        return job_service.get_job(job_id)
    except IngestionJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/retry", response_model=IngestionJob)
def retry_ingestion_job(
    job_id: str,
    job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> IngestionJob:
    try:
        return job_service.retry(job_id)
    except IngestionJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/cancel", response_model=IngestionJob)
def cancel_ingestion_job(
    job_id: str,
    job_service: IngestionJobService = Depends(get_ingestion_job_service),
) -> IngestionJob:
    try:
        return job_service.cancel(job_id)
    except IngestionJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[DocumentRecord])
def list_documents(
    document_service: DocumentService = Depends(get_document_service),
) -> list[DocumentRecord]:
    return document_service.list_documents()


@router.get("/{doc_id}", response_model=DocumentRecord)
def get_document(
    doc_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentRecord:
    return document_service.get_document(doc_id)


@router.get("/{doc_id}/segments", response_model=list[DocumentSegment])
def list_segments(
    doc_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> list[DocumentSegment]:
    return document_service.get_segments(doc_id)


@router.get("/{doc_id}/knowledge-graph", response_model=DocumentKnowledgeGraph)
def get_knowledge_graph(
    doc_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentKnowledgeGraph:
    return document_service.get_knowledge_graph(doc_id)
