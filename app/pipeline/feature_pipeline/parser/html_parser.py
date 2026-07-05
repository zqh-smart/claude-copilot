from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from app.pipeline.feature_pipeline.parser.helpers import with_parse_metadata
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    ParsedDocument,
    ParsedPageBlock,
    ParsedSection,
    ParsedTable,
)


class HtmlDocumentParser:
    def __init__(self, *, extract_tables: bool = True) -> None:
        self._extract_tables = extract_tables

    def parse(self, *, doc_id: str, content: bytes, metadata: DocumentMetadata) -> ParsedDocument:
        html = content.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        tables = self._build_tables(doc_id, soup) if self._extract_tables else []
        sections = self._build_sections(doc_id, soup)
        page_blocks = self._build_page_blocks(doc_id, soup, tables)

        raw_parts = [section.content for section in sections if section.content.strip()]
        raw_parts.extend(table.raw_markdown or "" for table in tables)
        raw_text = "\n\n".join(part for part in raw_parts if part.strip())

        return ParsedDocument(
            doc_id=doc_id,
            metadata=with_parse_metadata(
                metadata,
                parse_backend="native-html",
                parse_route="native_html",
                page_count=1,
                parsed_page_range=(1, 1),
                parsed_page_count=1,
            ),
            raw_text=raw_text,
            sections=sections,
            page_blocks=page_blocks,
            tables=tables,
        )

    def _build_sections(self, doc_id: str, soup: BeautifulSoup) -> list[ParsedSection]:
        body = soup.body or soup
        default_title = soup.title.get_text(" ", strip=True) if soup.title else "HTML Content"
        sections: list[ParsedSection] = []
        current_title = default_title
        current_lines: list[str] = []

        for element in self._iter_structural_elements(body):
            text = element.get_text(" ", strip=True)
            if not text:
                continue

            block_type = self._classify_text_block(element, text)
            if block_type == "heading":
                if current_lines:
                    sections.append(
                        ParsedSection(
                            section_id=f"{doc_id}-section-{len(sections) + 1}",
                            title=current_title,
                            content="\n".join(current_lines).strip(),
                            section_type="html_section",
                            page_start=1,
                            page_end=1,
                        )
                    )
                    current_lines = []
                current_title = text
            else:
                current_lines.append(text)

        if current_lines:
            sections.append(
                ParsedSection(
                    section_id=f"{doc_id}-section-{len(sections) + 1}",
                    title=current_title,
                    content="\n".join(current_lines).strip(),
                    section_type="html_section",
                    page_start=1,
                    page_end=1,
                )
            )

        if not sections:
            fallback_text = body.get_text("\n", strip=True)
            sections.append(
                ParsedSection(
                    section_id=f"{doc_id}-section-1",
                    title=default_title,
                    content=fallback_text,
                    section_type="html_section",
                    page_start=1,
                    page_end=1,
                )
            )

        return sections

    def _build_tables(self, doc_id: str, soup: BeautifulSoup) -> list[ParsedTable]:
        tables: list[ParsedTable] = []
        for index, table in enumerate(soup.find_all("table"), start=1):
            rows: list[list[str]] = []
            for tr in table.find_all("tr"):
                cells = tr.find_all(["th", "td"])
                row = [cell.get_text(" ", strip=True) for cell in cells]
                if any(cell for cell in row):
                    rows.append(row)

            if not rows:
                continue

            caption_tag = table.find("caption")
            caption = caption_tag.get_text(" ", strip=True) if caption_tag else None
            contextual_title = self._find_table_context_title(table) if not caption else None

            tables.append(
                ParsedTable(
                    table_id=f"{doc_id}-html-table-{index}",
                    table_type="html_table",
                    title=caption or contextual_title,
                    raw_markdown=self._table_to_markdown(rows),
                    page=1,
                    headers=rows[0],
                    rows=rows[1:] if len(rows) > 1 else [],
                    metadata={
                        "row_count": len(rows),
                        "column_count": max((len(row) for row in rows), default=0),
                        "dom_index": index,
                        "title_source": "caption" if caption else ("context" if contextual_title else None),
                    },
                )
            )

        return tables

    def _build_page_blocks(
        self,
        doc_id: str,
        soup: BeautifulSoup,
        tables: list[ParsedTable],
    ) -> list[ParsedPageBlock]:
        body = soup.body or soup
        blocks: list[ParsedPageBlock] = []
        order = 0
        current_heading: str | None = None

        table_block_ids_by_dom_index = {
            table.metadata.get("dom_index"): table for table in tables if table.metadata.get("dom_index") is not None
        }
        table_dom_index = 0

        for element in self._iter_structural_elements(body, include_tables=True):
            if element.name == "table":
                table_dom_index += 1
                rows: list[list[str]] = []
                for tr in element.find_all("tr"):
                    cells = tr.find_all(["th", "td"])
                    row = [cell.get_text(" ", strip=True) for cell in cells]
                    if any(cell for cell in row):
                        rows.append(row)
                table_text = self._table_to_markdown(rows)
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
                matched_table = table_block_ids_by_dom_index.get(table_dom_index)
                if matched_table is not None:
                    matched_table.source_block_id = block_id
                    if not matched_table.title and current_heading:
                        matched_table.title = current_heading
                        matched_table.metadata["title_source"] = "page_block_heading"
                continue

            text = element.get_text(" ", strip=True)
            if not text:
                continue

            block_type = self._classify_text_block(element, text)

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
            if block_type == "heading":
                current_heading = text

        return blocks

    def _iter_structural_elements(self, body: BeautifulSoup | Tag, *, include_tables: bool = False) -> list[Tag]:
        allowed_tags = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "div"]
        if include_tables:
            allowed_tags.append("table")

        elements: list[Tag] = []
        block_like_descendants = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "div", "table"}

        for element in body.find_all(allowed_tags):
            if not isinstance(element, Tag) or element.find_parent("table") is not None:
                continue
            if element.name == "div":
                has_nested_block = any(
                    descendant is not element
                    and isinstance(descendant, Tag)
                    and descendant.name in block_like_descendants
                    and descendant.get_text(" ", strip=True)
                    for descendant in element.find_all(block_like_descendants)
                )
                if has_nested_block:
                    continue
            elements.append(element)

        return elements

    def _classify_text_block(self, element: Tag, text: str) -> str:
        if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return "heading"
        if element.name == "li":
            return "list_item"
        if element.name == "blockquote":
            return "blockquote"
        if self._looks_like_heading_text(text):
            return "heading"
        return "paragraph"

    def _looks_like_heading_text(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return False
        lower = normalized.lower()
        if len(normalized) > 160:
            return False

        if re.match(r"^(form 10-k|part [ivx]+|item \d+[a-z]?[.\s]|note \d+[a-z]?)", lower):
            return True

        heading_prefixes = (
            "consolidated ",
            "income statement",
            "balance sheet",
            "cash flow statement",
            "statement of",
            "statements of",
            "notes to financial statements",
            "notes to consolidated financial statements",
            "management discussion",
            "risk factors",
        )
        if any(lower.startswith(marker) for marker in heading_prefixes):
            return True
        if len(normalized) <= 80 and normalized == normalized.upper() and re.search(r"[A-Z]{3,}", normalized):
            return True
        return False

    def _find_table_context_title(self, table: Tag) -> str | None:
        sibling: Tag | None = table
        for _ in range(5):
            sibling = sibling.find_previous_sibling() if sibling is not None else None
            if sibling is None:
                break
            if not isinstance(sibling, Tag) or sibling.name in {"script", "style"}:
                continue
            text = sibling.get_text(" ", strip=True)
            if not text:
                continue
            if len(text) > 180:
                continue
            if self._looks_like_heading_text(text) or sibling.name in {"b", "strong", "h1", "h2", "h3", "h4", "h5", "h6"}:
                return text
        return None

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
