from app.core.config import get_settings
from app.pipeline.feature_pipeline.parser.extract_processor import ExtractProcessor
from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument


class ParserRouter:
    def __init__(self) -> None:
        settings = get_settings()
        backend_priority = [
            item.strip().lower()
            for item in settings.pdf_parser_backend_priority.split(",")
            if item.strip()
        ]
        self._extract_processor = ExtractProcessor(
            pdf_backend_priority=backend_priority,
            markdown_split_by_headers=settings.markdown_split_by_headers,
            docx_extract_tables=settings.docx_extract_tables,
        )

    def parse(
        self,
        *,
        doc_id: str,
        filename: str,
        content: bytes,
        metadata: DocumentMetadata,
    ) -> ParsedDocument:
        return self._extract_processor.extract(
            doc_id=doc_id,
            filename=filename,
            content=content,
            metadata=metadata,
        )
