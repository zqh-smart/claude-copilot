from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.pipeline.feature_pipeline.parser.helpers import with_parse_metadata
from app.pipeline.feature_pipeline.parser.pptx_parser import PptxDocumentParser
from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument


class PptDocumentParser:
    def __init__(self) -> None:
        self._pptx_parser = PptxDocumentParser()

    def parse(self, *, doc_id: str, content: bytes, metadata: DocumentMetadata) -> ParsedDocument:
        pptx_content = self._convert_ppt_to_pptx_content(content)
        parsed = self._pptx_parser.parse(doc_id=doc_id, content=pptx_content, metadata=metadata)
        parsed.metadata = with_parse_metadata(
            parsed.metadata,
            parse_backend="win32com-powerpoint",
            parse_route="native_ppt",
            page_count=parsed.metadata.page_count,
            parsed_page_range=parsed.metadata.parsed_page_range,
            parsed_page_count=parsed.metadata.parsed_page_count,
            content_quality_score=parsed.metadata.content_quality_score,
        )
        return parsed

    def _convert_ppt_to_pptx_content(self, content: bytes) -> bytes:
        import pythoncom
        import win32com.client

        with TemporaryDirectory(prefix="claude-copilot-ppt-") as temp_dir:
            source_path = Path(temp_dir) / "source.ppt"
            target_path = Path(temp_dir) / "converted.pptx"
            source_path.write_bytes(content)

            pythoncom.CoInitialize()
            powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
            powerpoint.Visible = 0
            presentation = None
            try:
                presentation = powerpoint.Presentations.Open(str(source_path), WithWindow=False)
                presentation.SaveAs(str(target_path), 24)
            finally:
                if presentation is not None:
                    presentation.Close()
                powerpoint.Quit()
                pythoncom.CoUninitialize()

            return target_path.read_bytes()
