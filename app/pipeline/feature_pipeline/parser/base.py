from typing import Protocol

from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument


class DocumentParser(Protocol):
    def parse(self, *, doc_id: str, content: bytes, metadata: DocumentMetadata) -> ParsedDocument:
        ...
