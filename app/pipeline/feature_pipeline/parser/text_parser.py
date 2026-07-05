from app.pipeline.feature_pipeline.parser.helpers import with_parse_metadata
from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument, ParsedSection


class TextDocumentParser:
    def parse(self, *, doc_id: str, content: bytes, metadata: DocumentMetadata) -> ParsedDocument:
        text = content.decode("utf-8", errors="ignore")
        sections = [
            ParsedSection(
                section_id=f"{doc_id}-section-1",
                title="Text Content",
                content=text,
            )
        ]
        return ParsedDocument(
            doc_id=doc_id,
            metadata=with_parse_metadata(metadata, parse_backend="native-text", parse_route="native_text"),
            raw_text=text,
            sections=sections,
        )
