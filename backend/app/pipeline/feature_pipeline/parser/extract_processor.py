from pathlib import Path

from app.core.errors import UnsupportedDocumentTypeError
from app.pipeline.feature_pipeline.parser.doc_parser import DocDocumentParser
from app.pipeline.feature_pipeline.parser.docx_parser import DocxDocumentParser
from app.pipeline.feature_pipeline.parser.html_parser import HtmlDocumentParser
from app.pipeline.feature_pipeline.parser.markdown_parser import MarkdownDocumentParser
from app.pipeline.feature_pipeline.parser.pdf_parser import PdfDocumentParser
from app.pipeline.feature_pipeline.parser.ppt_parser import PptDocumentParser
from app.pipeline.feature_pipeline.parser.pptx_parser import PptxDocumentParser
from app.pipeline.feature_pipeline.parser.spreadsheet_parser import SpreadsheetDocumentParser
from app.pipeline.feature_pipeline.parser.text_parser import TextDocumentParser
from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument


class ExtractProcessor:
    """Dify-style extractor router for local document ingestion."""

    def __init__(
        self,
        *,
        pdf_backend_priority: list[str] | None = None,
        markdown_split_by_headers: bool = True,
        docx_extract_tables: bool = True,
    ) -> None:
        self._handlers = {
            ".txt": TextDocumentParser(),
            ".md": MarkdownDocumentParser(split_by_headers=markdown_split_by_headers),
            ".markdown": MarkdownDocumentParser(split_by_headers=markdown_split_by_headers),
            ".mdx": MarkdownDocumentParser(split_by_headers=markdown_split_by_headers),
            ".html": HtmlDocumentParser(),
            ".htm": HtmlDocumentParser(),
            ".pdf": PdfDocumentParser(backend_priority=pdf_backend_priority),
            ".docx": DocxDocumentParser(extract_tables=docx_extract_tables),
            ".docm": DocxDocumentParser(extract_tables=docx_extract_tables),
            ".doc": DocDocumentParser(),
            ".xlsx": SpreadsheetDocumentParser(),
            ".xlsm": SpreadsheetDocumentParser(),
            ".xls": SpreadsheetDocumentParser(),
            ".pptx": PptxDocumentParser(),
            ".pptm": PptxDocumentParser(),
            ".ppt": PptDocumentParser(),
        }

    def extract(
        self,
        *,
        doc_id: str,
        filename: str,
        content: bytes,
        metadata: DocumentMetadata,
    ) -> ParsedDocument:
        extension = Path(filename).suffix.lower()
        parser = self._handlers.get(extension)
        if parser is None:
            raise UnsupportedDocumentTypeError(f"Unsupported document type: {extension or 'unknown'}")
        return parser.parse(doc_id=doc_id, content=content, metadata=metadata)
