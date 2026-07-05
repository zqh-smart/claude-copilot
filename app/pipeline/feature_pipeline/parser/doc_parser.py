from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.pipeline.feature_pipeline.parser.docx_parser import DocxDocumentParser
from app.pipeline.feature_pipeline.parser.helpers import with_parse_metadata
from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument


class DocDocumentParser:
    def __init__(self) -> None:
        self._docx_parser = DocxDocumentParser(extract_tables=True)

    def parse(self, *, doc_id: str, content: bytes, metadata: DocumentMetadata) -> ParsedDocument:
        docx_content = self._convert_doc_to_docx_content(content)
        parsed = self._docx_parser.parse(doc_id=doc_id, content=docx_content, metadata=metadata)
        parsed.metadata = with_parse_metadata(
            parsed.metadata,
            parse_backend="win32com-word",
            parse_route="native_doc",
            page_count=parsed.metadata.page_count,
            parsed_page_range=parsed.metadata.parsed_page_range,
            parsed_page_count=parsed.metadata.parsed_page_count,
            content_quality_score=parsed.metadata.content_quality_score,
        )
        return parsed

    def _convert_doc_to_docx_content(self, content: bytes) -> bytes:
        import pythoncom
        import win32com.client

        with TemporaryDirectory(prefix="claude-copilot-doc-") as temp_dir:
            source_path = Path(temp_dir) / "source.doc"
            target_path = Path(temp_dir) / "converted.docx"
            source_path.write_bytes(content)

            pythoncom.CoInitialize()
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            document = None
            try:
                document = word.Documents.Open(str(source_path), ReadOnly=True, AddToRecentFiles=False)
                document.SaveAs2(str(target_path), FileFormat=16)
            finally:
                if document is not None:
                    document.Close(False)
                word.Quit()
                pythoncom.CoUninitialize()

            return target_path.read_bytes()
