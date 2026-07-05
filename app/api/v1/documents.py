from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import get_document_service
from app.api.services import DocumentService
from src.claude_copilot.schemas.document import DocumentRecord, DocumentSegment
from src.claude_copilot.schemas.knowledge_graph import DocumentKnowledgeGraph

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentRecord)
async def upload_document(
    file: UploadFile = File(...),
    company: str | None = Form(default=None),
    year: int | None = Form(default=None),
    doc_type: str = Form(default="financial_report"),
    source: str = Form(default="upload"),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentRecord:
    return await document_service.upload_document(
        file=file,
        company=company,
        year=year,
        doc_type=doc_type,
        source=source,
    )


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
