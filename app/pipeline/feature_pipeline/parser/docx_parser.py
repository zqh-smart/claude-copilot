from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.pipeline.feature_pipeline.parser.helpers import with_parse_metadata
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    ParsedDocument,
    ParsedPageBlock,
    ParsedSection,
    ParsedTable,
)


class DocxDocumentParser:
    def __init__(self, *, extract_tables: bool = True) -> None:
        self._extract_tables = extract_tables

    def parse(self, *, doc_id: str, content: bytes, metadata: DocumentMetadata) -> ParsedDocument:
        from io import BytesIO

        document = Document(BytesIO(content))
        layout_items = list(self._iter_layout_items(document))
        paragraphs = [
            item for item in layout_items if isinstance(item, Paragraph) and item.text.strip()
        ]
        sections = self._build_sections(doc_id, paragraphs)
        tables = self._build_tables(layout_items) if self._extract_tables else []
        page_blocks = self._build_page_blocks(doc_id, layout_items, tables)

        raw_parts = [section.content for section in sections]
        raw_parts.extend(table.raw_markdown or "" for table in tables)
        raw_text = "\n\n".join(part for part in raw_parts if part.strip())

        return ParsedDocument(
            doc_id=doc_id,
            metadata=with_parse_metadata(
                metadata,
                parse_backend="native-docx",
                parse_route="native_docx",
                page_count=1,
                parsed_page_range=(1, 1),
                parsed_page_count=1,
            ),
            raw_text=raw_text,
            sections=sections,
            page_blocks=page_blocks,
            tables=tables,
        )

    def _build_sections(self, doc_id: str, paragraphs: list) -> list[ParsedSection]:
        sections: list[ParsedSection] = []
        current_title = "DOCX Content"
        current_lines: list[str] = []

        for paragraph in paragraphs:
            style_name = getattr(paragraph.style, "name", "") or ""
            is_heading = style_name.lower().startswith("heading")
            if is_heading:
                if current_lines:
                    sections.append(
                        ParsedSection(
                            section_id=f"{doc_id}-section-{len(sections) + 1}",
                            title=current_title,
                            content="\n".join(current_lines).strip(),
                            section_type="docx_section",
                            page_start=1,
                            page_end=1,
                        )
                    )
                    current_lines = []
                current_title = paragraph.text.strip()
            else:
                current_lines.append(paragraph.text.strip())

        if current_lines:
            sections.append(
                ParsedSection(
                    section_id=f"{doc_id}-section-{len(sections) + 1}",
                    title=current_title,
                    content="\n".join(current_lines).strip(),
                    section_type="docx_section",
                    page_start=1,
                    page_end=1,
                )
            )

        if not sections:
            sections.append(
                ParsedSection(
                    section_id=f"{doc_id}-section-1",
                    title="DOCX Content",
                    content="",
                    section_type="docx_section",
                    page_start=1,
                    page_end=1,
                )
            )
        return sections

    def _iter_layout_items(self, document) -> list[Paragraph | Table]:
        items: list[Paragraph | Table] = []
        for child in document.element.body.iterchildren():
            if isinstance(child, CT_P):
                items.append(Paragraph(child, document))
            elif isinstance(child, CT_Tbl):
                items.append(Table(child, document))
        return items

    def _build_tables(self, layout_items: list[Paragraph | Table]) -> list[ParsedTable]:
        tables: list[ParsedTable] = []
        current_heading: str | None = None
        for item in layout_items:
            if isinstance(item, Paragraph):
                style_name = getattr(item.style, "name", "") or ""
                if item.text.strip() and style_name.lower().startswith("heading"):
                    current_heading = item.text.strip()
                continue

            table = item
            rows = []
            for row in table.rows:
                rows.append([cell.text.strip().replace("\n", " ") for cell in row.cells])
            markdown = self._table_to_markdown(rows)
            tables.append(
                ParsedTable(
                    table_id=f"docx-table-{len(tables) + 1}",
                    table_type="docx_table",
                    title=current_heading,
                    raw_markdown=markdown,
                    page=1,
                    headers=rows[0] if rows else [],
                    rows=rows[1:] if len(rows) > 1 else [],
                    metadata={
                        "row_count": len(rows),
                        "column_count": max((len(row) for row in rows), default=0),
                        "title_source": "preceding_heading" if current_heading else None,
                    },
                )
            )
        return tables

    def _build_page_blocks(
        self,
        doc_id: str,
        layout_items: list[Paragraph | Table],
        tables: list[ParsedTable],
    ) -> list[ParsedPageBlock]:
        blocks: list[ParsedPageBlock] = []
        order = 0
        table_index = 0

        for item in layout_items:
            if isinstance(item, Paragraph):
                text = item.text.strip()
                if not text:
                    continue
                style_name = getattr(item.style, "name", "") or ""
                block_type = "heading" if style_name.lower().startswith("heading") else "paragraph"
                order += 1
                blocks.append(
                    ParsedPageBlock(
                        block_id=f"{doc_id}-page-1-block-{order}",
                        block_type=block_type,
                        text=text,
                        page=1,
                        order=order,
                    )
                )
                continue

            if table_index >= len(tables):
                continue
            table = tables[table_index]
            table_index += 1
            table_text = table.raw_markdown or ""
            if not table_text.strip():
                continue
            order += 1
            block_id = f"{doc_id}-page-1-block-{order}"
            blocks.append(
                ParsedPageBlock(
                    block_id=block_id,
                    block_type="table",
                    text=table_text,
                    page=1,
                    order=order,
                )
            )
            table.source_block_id = block_id

        return blocks

    @staticmethod
    def _table_to_markdown(rows: list[list[str]]) -> str:
        if not rows:
            return ""
        width = max(len(row) for row in rows)
        normalized = [row + [""] * (width - len(row)) for row in rows]
        header = normalized[0]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * width) + " |",
        ]
        for row in normalized[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)
