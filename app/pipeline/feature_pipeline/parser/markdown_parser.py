import re

from app.pipeline.feature_pipeline.parser.helpers import with_parse_metadata
from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument, ParsedSection


class MarkdownDocumentParser:
    def __init__(self, *, split_by_headers: bool = True) -> None:
        self._split_by_headers = split_by_headers

    def parse(self, *, doc_id: str, content: bytes, metadata: DocumentMetadata) -> ParsedDocument:
        text = content.decode("utf-8", errors="ignore")
        sections = self._parse_sections(doc_id, text)

        return ParsedDocument(
            doc_id=doc_id,
            metadata=with_parse_metadata(
                metadata,
                parse_backend="native-markdown",
                parse_route="native_markdown",
            ),
            raw_text=text,
            sections=sections,
        )

    def _parse_sections(self, doc_id: str, text: str) -> list[ParsedSection]:
        if not self._split_by_headers:
            return [
                ParsedSection(
                    section_id=f"{doc_id}-section-1",
                    title="Markdown Content",
                    content=text.strip(),
                )
            ]

        lines = text.splitlines()
        sections: list[ParsedSection] = []
        current_title: str | None = None
        current_body: list[str] = []
        in_code_block = False

        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                current_body.append(line)
                continue

            is_header = bool(re.match(r"^#{1,6}\s+", line)) and not in_code_block
            if is_header:
                if current_title is not None or any(item.strip() for item in current_body):
                    sections.append(
                        ParsedSection(
                            section_id=f"{doc_id}-section-{len(sections) + 1}",
                            title=current_title,
                            content="\n".join(current_body).strip(),
                        )
                    )
                current_title = re.sub(r"^#{1,6}\s+", "", line).strip()
                current_body = []
            else:
                current_body.append(line)

        if current_title is not None or any(item.strip() for item in current_body):
            sections.append(
                ParsedSection(
                    section_id=f"{doc_id}-section-{len(sections) + 1}",
                    title=current_title or "Markdown Content",
                    content="\n".join(current_body).strip(),
                )
            )

        if not sections:
            sections.append(
                ParsedSection(
                    section_id=f"{doc_id}-section-1",
                    title="Markdown Content",
                    content=text.strip(),
                )
            )
        return sections
