from fastapi import APIRouter, Depends

from app.api.dependencies import get_research_service
from app.api.services import ResearchService
from src.claude_copilot.schemas.research import ResearchPreviewRequest, ResearchPreviewResponse

router = APIRouter(prefix="/api/v1/research", tags=["research"])


@router.post("/preview", response_model=ResearchPreviewResponse)
def preview_research(
    request: ResearchPreviewRequest,
    research_service: ResearchService = Depends(get_research_service),
) -> ResearchPreviewResponse:
    return research_service.preview(
        doc_id=request.doc_id,
        question=request.question,
        top_k=request.top_k,
    )


@router.post("/query", response_model=ResearchPreviewResponse)
def query_research(
    request: ResearchPreviewRequest,
    research_service: ResearchService = Depends(get_research_service),
) -> ResearchPreviewResponse:
    return research_service.preview(
        doc_id=request.doc_id,
        question=request.question,
        top_k=request.top_k,
    )
