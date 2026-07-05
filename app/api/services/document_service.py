from fastapi import UploadFile

from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService
from src.claude_copilot.schemas.document import DocumentRecord, DocumentSegment


class DocumentService:
    def __init__(self, pipeline_service: DocumentPipelineService) -> None:
        self._pipeline_service = pipeline_service

    async def upload_document(
        self,
        *,
        file: UploadFile,
        company: str | None,
        year: int | None,
        doc_type: str,
        source: str,
    ) -> DocumentRecord:
        content = await file.read()
        return self._pipeline_service.ingest(
            filename=file.filename or "uploaded_document",
            content_type=file.content_type,
            content=content,
            company=company,
            year=year,
            doc_type=doc_type,
            source=source,
        )

    def list_documents(self) -> list[DocumentRecord]:
        return self._pipeline_service.list_documents()

    def get_document(self, doc_id: str) -> DocumentRecord:
        return self._pipeline_service.get_document(doc_id)

    def get_segments(self, doc_id: str) -> list[DocumentSegment]:
        return self._pipeline_service.get_segments(doc_id)

    def get_knowledge_graph(self, doc_id: str):
        return self._pipeline_service.get_knowledge_graph(doc_id)
