from __future__ import annotations

import hashlib
import html as html_lib
import importlib
import inspect
import json
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader

from app.pipeline.feature_pipeline.parser.helpers import with_parse_metadata
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    ParsedDocument,
    ParsedPageBlock,
    ParsedSection,
    ParsedTable,
    ParseIssue,
    ParseQualityReport,
)


@dataclass(slots=True)
class PdfPageProfile:
    page_number: int
    text: str
    lines: list[str]
    table_groups: list[list[str]]

    @property
    def char_count(self) -> int:
        return len(self.text.strip())

    @property
    def has_text(self) -> bool:
        return self.char_count > 0

    @property
    def table_line_count(self) -> int:
        return sum(len(group) for group in self.table_groups)

    @property
    def non_empty_lines(self) -> list[str]:
        return [line.strip() for line in self.lines if line.strip()]


@dataclass(slots=True)
class MineruParseArtifacts:
    markdown_text: str = ""
    page_blocks: list[ParsedPageBlock] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)


class PdfDocumentParser:
    ROUTE_ALIASES = {
        "native": "native_pdf",
        "native-pdf": "native_pdf",
        "pypdf": "native_pdf",
        "ocr": "ocr_pdf",
        "ocr-pdf": "ocr_pdf",
        "table": "table_pdf",
        "table-pdf": "table_pdf",
        "mineru": "mineru_pdf",
        "mineru-pdf": "mineru_pdf",
        "magic_pdf": "mineru_pdf",
        "unstructured": "native_pdf",
    }

    MINERU_MODULE_PATHS = (
        "mineru.cli.common",
        "magic_pdf.cli.common",
    )

    CAPTION_BLOCK_TYPES = {"table_caption", "figure_caption"}

    def __init__(
        self,
        *,
        backend_priority: list[str] | None = None,
        mineru_start_page_id: int = 0,
        mineru_end_page_id: int | None = None,
    ) -> None:
        raw_priority = backend_priority or ["mineru_pdf", "table_pdf", "native_pdf", "ocr_pdf"]
        self._backend_priority = self._normalize_priority(raw_priority)
        self._mineru_start_page_id = mineru_start_page_id
        self._mineru_end_page_id = mineru_end_page_id

    def parse(self, *, doc_id: str, content: bytes, metadata: DocumentMetadata) -> ParsedDocument:
        page_profiles = self._build_page_profiles(content)
        route = self._select_route(page_profiles)
        effective_page_profiles = self._get_effective_page_profiles(page_profiles=page_profiles, route=route)

        if route == "mineru_pdf":
            parsed_document = self._parse_mineru_pdf(
                doc_id=doc_id,
                content=content,
                metadata=metadata,
                page_profiles=page_profiles,
            )
        elif route == "ocr_pdf":
            parsed_document = self._parse_ocr_pdf(
                doc_id=doc_id,
                content=content,
                metadata=metadata,
                page_profiles=page_profiles,
            )
        elif route == "table_pdf":
            parsed_document = self._parse_table_pdf(
                doc_id=doc_id,
                metadata=metadata,
                page_profiles=page_profiles,
            )
        else:
            parsed_document = self._parse_native_pdf(
                doc_id=doc_id,
                metadata=metadata,
                page_profiles=page_profiles,
            )

        return self._finalize_document(
            parsed_document=parsed_document,
            page_profiles=page_profiles,
            effective_page_profiles=effective_page_profiles,
            route=route,
        )

    def _normalize_priority(self, backend_priority: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in backend_priority:
            key = self.ROUTE_ALIASES.get(item.strip().lower(), item.strip().lower())
            if key and key not in normalized:
                normalized.append(key)
        if "native_pdf" not in normalized:
            normalized.append("native_pdf")
        return normalized

    def _build_page_profiles(self, content: bytes) -> list[PdfPageProfile]:
        scan_profiles = self._build_scan_page_profiles(content)
        if scan_profiles is not None:
            return scan_profiles

        reader = PdfReader(BytesIO(content))
        page_profiles: list[PdfPageProfile] = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            lines = [line.rstrip() for line in text.splitlines()]
            table_groups = self._detect_table_groups(lines)
            page_profiles.append(
                PdfPageProfile(
                    page_number=page_number,
                    text=text,
                    lines=lines,
                    table_groups=table_groups,
                )
            )

        return page_profiles

    def _build_scan_page_profiles(self, content: bytes) -> list[PdfPageProfile] | None:
        """Fast-path image-only PDFs without paying pypdf's full-page extraction cost."""
        try:
            import fitz
        except Exception:
            return None

        document = fitz.open(stream=content, filetype="pdf")
        profiles: list[PdfPageProfile] = []
        try:
            for page_number, page in enumerate(document, start=1):
                text = page.get_text("text") or ""
                if text.strip():
                    return None
                profiles.append(
                    PdfPageProfile(
                        page_number=page_number,
                        text="",
                        lines=[],
                        table_groups=[],
                    )
                )
        finally:
            document.close()

        return profiles

    def _select_route(self, page_profiles: list[PdfPageProfile]) -> str:
        needs_ocr = self._should_use_ocr(page_profiles)
        text_rich = self._text_coverage(page_profiles) >= 0.8
        has_tables = self._should_use_table_route(page_profiles)

        for route in self._backend_priority:
            if route == "mineru_pdf" and self._can_use_mineru():
                # Prefer MinerU for weak/scan-like PDFs. For text-rich A-share
                # reports, fall through to table/native heuristics first.
                if needs_ocr or not text_rich:
                    return route
                continue
            if route == "ocr_pdf" and needs_ocr:
                return route
            if route == "table_pdf" and has_tables:
                return route
            if route == "native_pdf":
                return route

        return "native_pdf"

    def _text_coverage(self, page_profiles: list[PdfPageProfile]) -> float:
        if not page_profiles:
            return 0.0
        nonempty = sum(1 for profile in page_profiles if profile.has_text)
        return nonempty / len(page_profiles)

    def _get_effective_page_profiles(self, *, page_profiles: list[PdfPageProfile], route: str) -> list[PdfPageProfile]:
        if route != "mineru_pdf" or not page_profiles:
            return page_profiles

        total_pages = len(page_profiles)
        start_page_id = max(self._mineru_start_page_id, 0)
        if start_page_id >= total_pages:
            return []

        if self._mineru_end_page_id is None:
            end_page_id = total_pages - 1
        else:
            end_page_id = min(max(self._mineru_end_page_id, start_page_id), total_pages - 1)

        return page_profiles[start_page_id : end_page_id + 1]

    def _resolve_parsed_page_range(self, effective_page_profiles: list[PdfPageProfile]) -> tuple[int, int] | None:
        if not effective_page_profiles:
            return None

        return (effective_page_profiles[0].page_number, effective_page_profiles[-1].page_number)

    def _can_use_mineru(self) -> bool:
        return self._import_mineru_parse_module() is not None

    def _import_mineru_parse_module(self):
        for module_path in self.MINERU_MODULE_PATHS:
            try:
                return importlib.import_module(module_path)
            except Exception:
                continue
        return None

    def _should_use_ocr(self, page_profiles: list[PdfPageProfile]) -> bool:
        if not page_profiles:
            return False

        empty_pages = sum(1 for profile in page_profiles if not profile.has_text)
        total_pages = len(page_profiles)
        avg_chars = sum(profile.char_count for profile in page_profiles) / total_pages
        return empty_pages / total_pages >= 0.5 or avg_chars < 40

    def _should_use_table_route(self, page_profiles: list[PdfPageProfile]) -> bool:
        return any(profile.table_line_count >= 2 for profile in page_profiles)

    def _parse_native_pdf(
        self,
        *,
        doc_id: str,
        metadata: DocumentMetadata,
        page_profiles: list[PdfPageProfile],
    ) -> ParsedDocument:
        include_tables = self._should_use_table_route(page_profiles)
        sections = self._build_sections(doc_id=doc_id, page_profiles=page_profiles, section_type="pdf_page")
        page_blocks = self._build_page_blocks(
            doc_id=doc_id,
            page_profiles=page_profiles,
            include_tables=include_tables,
        )
        tables = (
            self._build_tables(doc_id=doc_id, page_profiles=page_profiles, page_blocks=page_blocks)
            if include_tables
            else []
        )
        raw_parts = [profile.text for profile in page_profiles if profile.text.strip()]
        raw_parts.extend(table.raw_markdown or "" for table in tables)

        return ParsedDocument(
            doc_id=doc_id,
            metadata=with_parse_metadata(
                metadata,
                parse_backend="pypdf",
                parse_route="native_pdf",
                page_count=len(page_profiles),
            ),
            raw_text="\n\n".join(part for part in raw_parts if part.strip()),
            sections=sections,
            page_blocks=page_blocks,
            tables=tables,
        )

    def _parse_table_pdf(
        self,
        *,
        doc_id: str,
        metadata: DocumentMetadata,
        page_profiles: list[PdfPageProfile],
    ) -> ParsedDocument:
        sections = self._build_sections(doc_id=doc_id, page_profiles=page_profiles, section_type="pdf_page")
        page_blocks = self._build_page_blocks(doc_id=doc_id, page_profiles=page_profiles, include_tables=True)
        tables = self._build_tables(doc_id=doc_id, page_profiles=page_profiles, page_blocks=page_blocks)

        raw_parts = [profile.text for profile in page_profiles if profile.text.strip()]
        raw_parts.extend(table.raw_markdown or "" for table in tables)

        return ParsedDocument(
            doc_id=doc_id,
            metadata=with_parse_metadata(
                metadata,
                parse_backend="pypdf-table-heuristic",
                parse_route="table_pdf",
                page_count=len(page_profiles),
            ),
            raw_text="\n\n".join(part for part in raw_parts if part.strip()),
            sections=sections,
            page_blocks=page_blocks,
            tables=tables,
        )

    def _parse_ocr_pdf(
        self,
        *,
        doc_id: str,
        content: bytes,
        metadata: DocumentMetadata,
        page_profiles: list[PdfPageProfile],
    ) -> ParsedDocument:
        ocr_texts = self._ocr_extract_page_texts(content)
        if ocr_texts:
            ocr_profiles = [
                PdfPageProfile(
                    page_number=index,
                    text=text,
                    lines=[line.rstrip() for line in text.splitlines()],
                    table_groups=self._detect_table_groups(text.splitlines()),
                )
                for index, text in enumerate(ocr_texts, start=1)
            ]
            sections = self._build_sections(doc_id=doc_id, page_profiles=ocr_profiles, section_type="pdf_page")
            page_blocks = self._build_page_blocks(doc_id=doc_id, page_profiles=ocr_profiles, include_tables=False)
            return ParsedDocument(
                doc_id=doc_id,
                metadata=with_parse_metadata(
                    metadata,
                    parse_backend="pymupdf+pytesseract",
                    parse_route="ocr_pdf",
                    page_count=len(ocr_profiles),
                ),
                raw_text="\n".join(profile.text for profile in ocr_profiles if profile.text.strip()),
                sections=sections,
                page_blocks=page_blocks,
            )

        parsed_document = self._parse_native_pdf(doc_id=doc_id, metadata=metadata, page_profiles=page_profiles)
        parsed_document.metadata = with_parse_metadata(
            parsed_document.metadata,
            parse_backend="pypdf-fallback",
            parse_route="ocr_pdf",
            page_count=len(page_profiles),
        )
        parsed_document.issues.append(
            ParseIssue(
                code="ocr_backend_unavailable",
                message="OCR route selected but OCR dependencies are unavailable, using native PDF fallback.",
                severity="warning",
            )
        )
        return parsed_document

    def _parse_mineru_pdf(
        self,
        *,
        doc_id: str,
        content: bytes,
        metadata: DocumentMetadata,
        page_profiles: list[PdfPageProfile],
    ) -> ParsedDocument:
        effective_page_profiles = self._get_effective_page_profiles(page_profiles=page_profiles, route="mineru_pdf")

        if not self._can_use_mineru():
            parsed_document = self._parse_table_pdf(
                doc_id=doc_id,
                metadata=metadata,
                page_profiles=effective_page_profiles or page_profiles,
            )
            parsed_document.metadata = with_parse_metadata(
                parsed_document.metadata,
                parse_backend="pypdf-table-fallback",
                parse_route="mineru_pdf",
                page_count=len(page_profiles),
            )
            parsed_document.issues.append(
                ParseIssue(
                    code="mineru_backend_unavailable",
                    message="MinerU route selected but MinerU is unavailable, using table-aware fallback.",
                    severity="warning",
                )
            )
            return parsed_document

        try:
            artifacts = self._run_mineru_parse(doc_id=doc_id, content=content)
        except Exception as exc:
            parsed_document = self._parse_table_pdf(
                doc_id=doc_id,
                metadata=metadata,
                page_profiles=effective_page_profiles or page_profiles,
            )
            parsed_document.metadata = with_parse_metadata(
                parsed_document.metadata,
                parse_backend="pypdf-table-fallback",
                parse_route="mineru_pdf",
                page_count=len(page_profiles),
            )
            parsed_document.issues.append(
                ParseIssue(
                    code="mineru_parse_failed",
                    message="MinerU parse failed, using table-aware fallback.",
                    severity="warning",
                    details={"error": str(exc)},
                )
            )
            return parsed_document

        scoped_page_profiles = effective_page_profiles or page_profiles
        sections = self._build_sections(doc_id=doc_id, page_profiles=scoped_page_profiles, section_type="pdf_page")
        page_blocks = artifacts.page_blocks or self._build_page_blocks(
            doc_id=doc_id,
            page_profiles=scoped_page_profiles,
            include_tables=True,
        )
        tables = artifacts.tables or self._build_tables(
            doc_id=doc_id,
            page_profiles=scoped_page_profiles,
            page_blocks=page_blocks,
        )
        raw_text = artifacts.markdown_text.strip() or "\n".join(
            profile.text for profile in scoped_page_profiles if profile.text.strip()
        )

        return ParsedDocument(
            doc_id=doc_id,
            metadata=with_parse_metadata(
                metadata,
                parse_backend="mineru",
                parse_route="mineru_pdf",
                page_count=len(page_profiles),
            ),
            raw_text=raw_text,
            sections=sections,
            page_blocks=page_blocks,
            tables=tables,
            issues=list(artifacts.issues),
        )

    def _run_mineru_parse(self, *, doc_id: str, content: bytes) -> MineruParseArtifacts:
        parse_module = self._import_mineru_parse_module()
        if parse_module is None or not hasattr(parse_module, "do_parse"):
            raise RuntimeError("MinerU parse module with do_parse is unavailable.")

        do_parse = getattr(parse_module, "do_parse")
        temp_root = Path.cwd() / ".tmp" / "mineru"
        temp_root.mkdir(parents=True, exist_ok=True)
        output_dir = temp_root / f"{doc_id}-mineru-run"
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._invoke_mineru_do_parse(do_parse=do_parse, output_dir=output_dir, filename=f"{doc_id}.pdf", content=content)
            return self._load_mineru_outputs(doc_id=doc_id, output_dir=output_dir)
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)

    def _invoke_mineru_do_parse(self, *, do_parse, output_dir: Path, filename: str, content: bytes) -> None:
        signature = inspect.signature(do_parse)
        params = signature.parameters

        kwargs: dict[str, Any] = {}
        if "output_dir" in params:
            kwargs["output_dir"] = str(output_dir)
        if "pdf_file_names" in params:
            kwargs["pdf_file_names"] = [filename]
        if "pdf_bytes_list" in params:
            kwargs["pdf_bytes_list"] = [content]
        if "pdf_bytes_md5_to_bytes" in params:
            content_md5 = hashlib.md5(content).hexdigest()  # noqa: S324
            kwargs["pdf_bytes_md5_to_bytes"] = {content_md5: content}
        if "p_lang_list" in params:
            kwargs["p_lang_list"] = ["ch"]
        if "parse_method" in params:
            kwargs["parse_method"] = "auto"
        if "formula_enable" in params:
            kwargs["formula_enable"] = True
        if "table_enable" in params:
            kwargs["table_enable"] = True
        if "start_page_id" in params:
            kwargs["start_page_id"] = self._mineru_start_page_id
        if "end_page_id" in params:
            kwargs["end_page_id"] = self._mineru_end_page_id

        pdf_image_tools = None
        original_executor_cls = None
        original_executor = None
        try:
            pdf_image_tools = importlib.import_module("mineru.utils.pdf_image_tools")
            original_executor_cls = getattr(pdf_image_tools, "ProcessPoolExecutor", None)
            original_executor = getattr(pdf_image_tools, "_pdf_render_executor", None)
            if original_executor is not None:
                try:
                    original_executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                pdf_image_tools._pdf_render_executor = None
            if original_executor_cls is not None:
                pdf_image_tools.ProcessPoolExecutor = ThreadPoolExecutor

            do_parse(**kwargs)
        finally:
            if pdf_image_tools is not None:
                current_executor = getattr(pdf_image_tools, "_pdf_render_executor", None)
                if current_executor is not None and current_executor is not original_executor:
                    try:
                        current_executor.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
                    pdf_image_tools._pdf_render_executor = None
                if original_executor_cls is not None:
                    pdf_image_tools.ProcessPoolExecutor = original_executor_cls

    def _load_mineru_outputs(self, *, doc_id: str, output_dir: Path) -> MineruParseArtifacts:
        markdown_files = sorted(output_dir.rglob("*.md"))
        json_files = sorted(output_dir.rglob("*.json"))
        zip_files = sorted(output_dir.rglob("*.zip"))

        if zip_files:
            extracted_dir = output_dir / "unzipped"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            for archive in zip_files:
                with zipfile.ZipFile(archive) as zip_ref:
                    zip_ref.extractall(extracted_dir)
            markdown_files = sorted(extracted_dir.rglob("*.md")) or markdown_files
            json_files = sorted(extracted_dir.rglob("*.json")) or json_files

        markdown_text = ""
        if markdown_files:
            markdown_text = max(
                (path.read_text(encoding="utf-8", errors="ignore") for path in markdown_files),
                key=len,
                default="",
            )

        json_payloads = [self._safe_load_json(path) for path in json_files]
        json_payloads = [payload for payload in json_payloads if payload is not None]

        page_blocks = self._parse_mineru_page_blocks(doc_id=doc_id, json_payloads=json_payloads)
        tables = self._parse_mineru_tables(doc_id=doc_id, json_payloads=json_payloads, page_blocks=page_blocks)

        issues: list[ParseIssue] = []
        if not markdown_text and not page_blocks:
            issues.append(
                ParseIssue(
                    code="mineru_empty_output",
                    message="MinerU returned no markdown or structured page blocks.",
                    severity="warning",
                )
            )

        return MineruParseArtifacts(
            markdown_text=markdown_text,
            page_blocks=page_blocks,
            tables=tables,
            issues=issues,
        )

    def _safe_load_json(self, path: Path) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return None

    def _parse_mineru_page_blocks(self, *, doc_id: str, json_payloads: list[Any]) -> list[ParsedPageBlock]:
        canonical_blocks = self._parse_mineru_page_blocks_from_page_payloads(doc_id=doc_id, json_payloads=json_payloads)
        if canonical_blocks:
            return canonical_blocks

        blocks: list[ParsedPageBlock] = []
        seen: set[tuple[Any, ...]] = set()
        order_by_page: defaultdict[int, int] = defaultdict(int)

        for item in self._iter_json_items(json_payloads):
            block_type = self._map_mineru_block_type(item)
            text = self._extract_text_like(item)
            if not block_type or not text:
                continue

            page = self._extract_page_number(item)
            if page is not None:
                page += self._mineru_start_page_id
            page_key = page or 0
            order_by_page[page_key] += 1
            order = order_by_page[page_key]
            bbox = self._extract_bbox(item)
            dedupe_key = (page, block_type, text)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            blocks.append(
                ParsedPageBlock(
                    block_id=f"{doc_id}-mineru-page-{page or 0}-block-{order}",
                    block_type=block_type,
                    text=text,
                    page=page,
                    order=order,
                    bbox=bbox,
                    metadata={"source": "mineru"},
                )
            )

        return sorted(blocks, key=lambda block: (block.page or 0, block.order or 0))

    def _parse_mineru_page_blocks_from_page_payloads(
        self,
        *,
        doc_id: str,
        json_payloads: list[Any],
    ) -> list[ParsedPageBlock]:
        blocks: list[ParsedPageBlock] = []
        seen: set[tuple[Any, ...]] = set()
        order_by_page: defaultdict[int, int] = defaultdict(int)

        for page, item in self._iter_mineru_page_items(json_payloads):
            block_type = self._map_mineru_block_type(item)
            text = self._extract_text_like(item)
            if not block_type or not text:
                continue

            bbox = self._extract_bbox(item)
            dedupe_key = (page, block_type, text, self._serialize_bbox(bbox))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            order_by_page[page] += 1
            order = order_by_page[page]
            blocks.append(
                ParsedPageBlock(
                    block_id=f"{doc_id}-mineru-page-{page}-block-{order}",
                    block_type=block_type,
                    text=text,
                    page=page,
                    order=order,
                    bbox=bbox,
                    metadata={"source": "mineru"},
                )
            )

        return sorted(blocks, key=lambda block: (block.page or 0, block.order or 0))

    def _parse_mineru_tables(
        self,
        *,
        doc_id: str,
        json_payloads: list[Any],
        page_blocks: list[ParsedPageBlock],
    ) -> list[ParsedTable]:
        canonical_tables = self._parse_mineru_tables_from_page_payloads(
            doc_id=doc_id,
            json_payloads=json_payloads,
            page_blocks=page_blocks,
        )
        if canonical_tables:
            return canonical_tables

        tables: list[ParsedTable] = []
        seen: set[tuple[int | None, str, str | None]] = set()
        caption_blocks_by_page = self._group_blocks_by_page(page_blocks=page_blocks, block_type="table_caption")
        footnote_blocks_by_page = self._group_blocks_by_page(page_blocks=page_blocks, block_type="footnote")

        for item in self._iter_json_items(json_payloads):
            block_type = self._map_mineru_block_type(item)
            if block_type != "table":
                continue

            page = self._extract_page_number(item)
            table_text = self._extract_text_like(item)
            headers, rows = self._extract_table_rows(item, table_text)
            raw_markdown = self._table_to_markdown([headers, *rows]) if headers else table_text
            bbox = self._extract_bbox(item)
            dedupe_key = (page, raw_markdown, self._serialize_bbox(bbox))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            table_index = len(tables) + 1
            caption_block = self._find_best_caption_block(
                page=page,
                table_bbox=bbox,
                caption_blocks=caption_blocks_by_page.get(page, []),
            )
            caption = caption_block.text if caption_block else None
            footnote_blocks = self._find_spatial_footnote_blocks(
                page=page,
                table_bbox=bbox,
                footnote_blocks=footnote_blocks_by_page.get(page, []),
            )
            block_id = self._find_matching_block_id(page_blocks=page_blocks, page=page, block_type="table", text=table_text)

            tables.append(
                ParsedTable(
                    table_id=f"{doc_id}-mineru-table-{table_index}",
                    table_type="mineru_table",
                    title=caption,
                    raw_markdown=raw_markdown,
                    page=page,
                    headers=headers,
                    rows=rows,
                    footnotes=[block.text for block in footnote_blocks],
                    source_block_id=block_id,
                    metadata={
                        "parse_mode": "mineru",
                        "row_count": len(rows) + (1 if headers else 0),
                        "column_count": len(headers),
                        "table_bbox": list(bbox) if bbox else None,
                        "caption_block_id": caption_block.block_id if caption_block else None,
                        "footnote_block_ids": [block.block_id for block in footnote_blocks],
                        "caption_binding": "bbox"
                        if caption_block and caption_block.bbox and bbox
                        else ("page_fallback" if caption_block else None),
                        "footnote_binding": "bbox"
                        if footnote_blocks and bbox and any(block.bbox for block in footnote_blocks)
                        else ("page_fallback" if footnote_blocks else None),
                    },
                )
            )

        return tables

    def _parse_mineru_tables_from_page_payloads(
        self,
        *,
        doc_id: str,
        json_payloads: list[Any],
        page_blocks: list[ParsedPageBlock],
    ) -> list[ParsedTable]:
        tables: list[ParsedTable] = []
        seen: set[tuple[int | None, str, str | None]] = set()
        caption_blocks_by_page = self._group_blocks_by_page(page_blocks=page_blocks, block_type="table_caption")
        footnote_blocks_by_page = self._group_blocks_by_page(page_blocks=page_blocks, block_type="footnote")

        for page, item in self._iter_mineru_page_items(json_payloads):
            raw_type = (
                item.get("block_type")
                or item.get("type")
                or item.get("category_type")
                or item.get("label")
                or item.get("kind")
            )
            if not isinstance(raw_type, str) or raw_type.strip().lower().replace("-", "_") != "table":
                continue

            table_text = self._extract_text_like(item)
            headers, rows = self._extract_table_rows(item, table_text)
            raw_markdown = self._table_to_markdown([headers, *rows]) if headers else table_text
            bbox = self._extract_bbox(item)
            dedupe_key = (page, raw_markdown, self._serialize_bbox(bbox))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            caption_block = self._find_best_caption_block(
                page=page,
                table_bbox=bbox,
                caption_blocks=caption_blocks_by_page.get(page, []),
            )
            inline_caption = self._extract_mineru_table_caption(item)
            caption = inline_caption or (caption_block.text if caption_block else None)
            inline_footnotes = self._extract_mineru_table_footnotes(item)
            footnote_blocks = self._find_spatial_footnote_blocks(
                page=page,
                table_bbox=bbox,
                footnote_blocks=footnote_blocks_by_page.get(page, []),
            )
            block_id = self._find_matching_block_id(page_blocks=page_blocks, page=page, block_type="table", text=table_text)

            tables.append(
                ParsedTable(
                    table_id=f"{doc_id}-mineru-table-{len(tables) + 1}",
                    table_type="mineru_table",
                    title=caption,
                    raw_markdown=raw_markdown,
                    page=page,
                    headers=headers,
                    rows=rows,
                    footnotes=inline_footnotes or [block.text for block in footnote_blocks],
                    source_block_id=block_id,
                    metadata={
                        "parse_mode": "mineru",
                        "raw_table_type": self._extract_mineru_raw_table_type(item),
                        "row_count": len(rows) + (1 if headers else 0),
                        "column_count": len(headers),
                        "table_bbox": list(bbox) if bbox else None,
                        "caption_block_id": caption_block.block_id if caption_block else None,
                        "footnote_block_ids": [block.block_id for block in footnote_blocks],
                        "caption_binding": "inline"
                        if inline_caption
                        else (
                            "bbox"
                            if caption_block and caption_block.bbox and bbox
                            else ("page_fallback" if caption_block else None)
                        ),
                        "footnote_binding": "inline"
                        if inline_footnotes
                        else (
                            "bbox"
                            if footnote_blocks and bbox and any(block.bbox for block in footnote_blocks)
                            else ("page_fallback" if footnote_blocks else None)
                        ),
                    },
                )
            )

        return tables

    def _iter_mineru_page_items(self, json_payloads: list[Any]) -> Iterable[tuple[int, dict[str, Any]]]:
        for payload in json_payloads:
            if not isinstance(payload, list):
                continue

            first_page_number = self._mineru_start_page_id + 1
            for page_index, page_items in enumerate(payload, start=first_page_number):
                if isinstance(page_items, list):
                    for item in page_items:
                        if isinstance(item, dict):
                            yield page_index, item

    def _serialize_bbox(self, bbox: tuple[float, float, float, float] | None) -> str | None:
        if bbox is None:
            return None
        return ",".join(f"{value:.2f}" for value in bbox)

    def _extract_mineru_table_caption(self, item: dict[str, Any]) -> str | None:
        content = item.get("content")
        if not isinstance(content, dict):
            return None

        caption_items = content.get("table_caption")
        if isinstance(caption_items, list):
            parts = [self._extract_text_like(part) for part in caption_items if isinstance(part, dict)]
            parts = [part for part in parts if part]
            if parts:
                return "\n".join(parts)

        return None

    def _extract_mineru_table_footnotes(self, item: dict[str, Any]) -> list[str]:
        content = item.get("content")
        if not isinstance(content, dict):
            return []

        footnote_items = content.get("table_footnote")
        if not isinstance(footnote_items, list):
            return []

        footnotes = [self._extract_text_like(part) for part in footnote_items if isinstance(part, dict)]
        return [footnote for footnote in footnotes if footnote]

    def _extract_mineru_raw_table_type(self, item: dict[str, Any]) -> str | None:
        content = item.get("content")
        if not isinstance(content, dict):
            return None

        raw_table_type = content.get("table_type")
        return raw_table_type.strip() if isinstance(raw_table_type, str) and raw_table_type.strip() else None

    def _iter_json_items(self, payloads: list[Any]) -> Iterable[dict[str, Any]]:
        for payload in payloads:
            yield from self._walk_json(payload)

    def _walk_json(self, value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from self._walk_json(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._walk_json(child)

    def _map_mineru_block_type(self, item: dict[str, Any]) -> str | None:
        raw_type = (
            item.get("block_type")
            or item.get("type")
            or item.get("category_type")
            or item.get("label")
            or item.get("kind")
        )
        if not isinstance(raw_type, str):
            return None

        block_type = raw_type.strip().lower().replace(" ", "_").replace("-", "_")
        mapping = {
            "title": "heading",
            "heading": "heading",
            "section_header": "heading",
            "header": "header",
            "page_header": "header",
            "footer": "footer",
            "page_footer": "footer",
            "paragraph": "paragraph",
            "text": "paragraph",
            "plain_text": "paragraph",
            "table": "table",
            "table_body": "table",
            "table_caption": "table_caption",
            "figure": "figure",
            "image": "figure",
            "figure_caption": "figure_caption",
            "caption": "figure_caption",
            "list": "list_item",
            "list_item": "list_item",
            "bullet_list": "list_item",
            "reference": "reference",
            "footnote": "footnote",
        }
        return mapping.get(block_type, block_type if block_type in {"heading", "paragraph", "table"} else None)

    def _extract_text_like(self, item: dict[str, Any]) -> str:
        for key in ("text", "content", "md", "markdown", "html", "latex", "value", "caption"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested_text = self._extract_text_from_nested_value(value)
                if nested_text:
                    return nested_text
            if isinstance(value, list):
                nested_parts = [self._extract_text_from_nested_value(part) for part in value]
                nested_parts = [part for part in nested_parts if part]
                if nested_parts:
                    return "\n".join(nested_parts)

        if isinstance(item.get("lines"), list):
            lines = [line.strip() for line in item["lines"] if isinstance(line, str) and line.strip()]
            if lines:
                return "\n".join(lines)

        return ""

    def _extract_text_from_nested_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("text", "content", "md", "markdown", "html", "latex", "value", "caption", "path"):
                nested = value.get(key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
                if isinstance(nested, (dict, list)):
                    nested_text = self._extract_text_from_nested_value(nested)
                    if nested_text:
                        return nested_text

            parts = [self._extract_text_from_nested_value(part) for part in value.values()]
            parts = [part for part in parts if part]
            return "\n".join(parts)

        if isinstance(value, list):
            parts = [self._extract_text_from_nested_value(part) for part in value]
            parts = [part for part in parts if part]
            return "\n".join(parts)

        return ""

    def _extract_page_number(self, item: dict[str, Any]) -> int | None:
        for key in ("page", "page_no", "page_num", "page_number", "page_idx"):
            value = item.get(key)
            if isinstance(value, int):
                return value + 1 if key == "page_idx" else value
            if isinstance(value, str) and value.isdigit():
                return int(value) + 1 if key == "page_idx" else int(value)
        return None

    def _extract_bbox(self, item: dict[str, Any]) -> tuple[float, float, float, float] | None:
        for key in ("bbox", "box", "coordinate", "coordinates"):
            value = item.get(key)
            if isinstance(value, list) and len(value) == 4:
                try:
                    return tuple(float(part) for part in value)  # type: ignore[return-value]
                except Exception:
                    return None
        return None

    def _extract_table_rows(self, item: dict[str, Any], fallback_text: str) -> tuple[list[str], list[list[str]]]:
        cells = item.get("rows") or item.get("table_rows") or item.get("data")
        if isinstance(cells, list) and cells:
            normalized: list[list[str]] = []
            for row in cells:
                if isinstance(row, list):
                    normalized_row = [str(cell).strip() for cell in row]
                    if any(cell for cell in normalized_row):
                        normalized.append(normalized_row)
            if normalized:
                normalized = self._normalize_rows(normalized)
                return normalized[0], normalized[1:]

        html_text = self._extract_mineru_table_html(item)
        if html_text:
            html_rows = self._extract_table_rows_from_html(html_text)
            if html_rows:
                normalized_rows = self._normalize_rows(html_rows)
                return normalized_rows[0], normalized_rows[1:]

        lines = [line for line in fallback_text.splitlines() if line.strip()]
        rows = [self._split_table_row(line) for line in lines]
        rows = [row for row in rows if len(row) >= 2]
        if not rows:
            return [], []
        normalized_rows = self._normalize_rows(rows)
        return normalized_rows[0], normalized_rows[1:]

    def _extract_mineru_table_html(self, item: dict[str, Any]) -> str:
        direct_html = item.get("html")
        if isinstance(direct_html, str) and direct_html.strip():
            return direct_html.strip()

        content = item.get("content")
        if isinstance(content, dict):
            html_value = content.get("html")
            if isinstance(html_value, str) and html_value.strip():
                return html_value.strip()

        return ""

    def _extract_table_rows_from_html(self, html_text: str) -> list[list[str]]:
        rows: list[list[str]] = []
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, flags=re.IGNORECASE | re.DOTALL):
            cell_htmls = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
            if not cell_htmls:
                continue
            normalized_row = [self._strip_html(cell_html) for cell_html in cell_htmls]
            if any(cell for cell in normalized_row):
                rows.append(normalized_row)
        return rows

    def _strip_html(self, value: str) -> str:
        cleaned = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = html_lib.unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _find_nearest_caption(
        self,
        *,
        page: int | None,
        captions_by_page: dict[tuple[int | None, int | None], str],
    ) -> str | None:
        matching = [text for (caption_page, _), text in captions_by_page.items() if caption_page == page]
        return matching[0] if matching else None

    def _group_blocks_by_page(
        self,
        *,
        page_blocks: list[ParsedPageBlock],
        block_type: str,
    ) -> dict[int, list[ParsedPageBlock]]:
        grouped: defaultdict[int, list[ParsedPageBlock]] = defaultdict(list)
        for block in page_blocks:
            if block.page is None or block.block_type != block_type:
                continue
            grouped[block.page].append(block)

        for blocks in grouped.values():
            blocks.sort(key=lambda block: (block.bbox[1] if block.bbox else float("inf"), block.order or 0))

        return dict(grouped)

    def _find_best_caption_block(
        self,
        *,
        page: int | None,
        table_bbox: tuple[float, float, float, float] | None,
        caption_blocks: list[ParsedPageBlock],
    ) -> ParsedPageBlock | None:
        if page is None or not caption_blocks:
            return None
        if table_bbox is None:
            return caption_blocks[0]

        ranked = sorted(
            caption_blocks,
            key=lambda block: self._caption_block_score(table_bbox=table_bbox, caption_block=block),
        )
        return ranked[0] if ranked else None

    def _caption_block_score(
        self,
        *,
        table_bbox: tuple[float, float, float, float],
        caption_block: ParsedPageBlock,
    ) -> tuple[float, float, float, int]:
        if caption_block.bbox is None:
            return (3.0, float("inf"), float("inf"), caption_block.order or 0)

        table_top = table_bbox[1]
        table_bottom = table_bbox[3]
        caption_top = caption_block.bbox[1]
        caption_bottom = caption_block.bbox[3]

        if caption_bottom <= table_top + 6:
            position_rank = 0.0
            vertical_gap = max(table_top - caption_bottom, 0.0)
        elif caption_top <= table_bottom:
            position_rank = 1.0
            vertical_gap = 0.0
        else:
            position_rank = 2.0
            vertical_gap = max(caption_top - table_bottom, 0.0)

        horizontal_distance = self._bbox_horizontal_distance(table_bbox, caption_block.bbox)
        return (position_rank, vertical_gap, horizontal_distance, caption_block.order or 0)

    def _find_spatial_footnote_blocks(
        self,
        *,
        page: int | None,
        table_bbox: tuple[float, float, float, float] | None,
        footnote_blocks: list[ParsedPageBlock],
    ) -> list[ParsedPageBlock]:
        if page is None or not footnote_blocks:
            return []
        if table_bbox is None:
            return footnote_blocks[:1]

        table_bottom = table_bbox[3]
        candidates = [
            block
            for block in footnote_blocks
            if block.bbox is not None
            and block.bbox[1] >= table_bottom - 6
            and (
                self._bbox_horizontal_overlap_ratio(table_bbox, block.bbox) >= 0.15
                or self._bbox_horizontal_distance(table_bbox, block.bbox) <= max((table_bbox[2] - table_bbox[0]) * 0.5, 80.0)
            )
        ]
        if not candidates:
            return footnote_blocks[:1]

        candidates.sort(
            key=lambda block: (
                max((block.bbox[1] if block.bbox else table_bottom) - table_bottom, 0.0),
                self._bbox_horizontal_distance(table_bbox, block.bbox),
                block.order or 0,
            )
        )
        bound_blocks = [candidates[0]]
        previous_bottom = candidates[0].bbox[3] if candidates[0].bbox else table_bottom
        for block in candidates[1:]:
            if block.bbox is None:
                continue
            if block.bbox[1] - previous_bottom > 24:
                break
            bound_blocks.append(block)
            previous_bottom = block.bbox[3]
        return bound_blocks

    def _bbox_horizontal_distance(
        self,
        left: tuple[float, float, float, float] | None,
        right: tuple[float, float, float, float] | None,
    ) -> float:
        if left is None or right is None:
            return float("inf")
        left_center = (left[0] + left[2]) / 2
        right_center = (right[0] + right[2]) / 2
        return abs(left_center - right_center)

    def _bbox_horizontal_overlap_ratio(
        self,
        left: tuple[float, float, float, float] | None,
        right: tuple[float, float, float, float] | None,
    ) -> float:
        if left is None or right is None:
            return 0.0

        overlap = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
        base_width = max(min(left[2] - left[0], right[2] - right[0]), 1.0)
        return overlap / base_width

    def _find_matching_block_id(
        self,
        *,
        page_blocks: list[ParsedPageBlock],
        page: int | None,
        block_type: str,
        text: str,
    ) -> str | None:
        for block in page_blocks:
            if block.page == page and block.block_type == block_type and block.text == text:
                return block.block_id
        return None

    def _ocr_extract_page_texts(self, content: bytes) -> list[str]:
        try:
            import fitz
            import pytesseract
            from PIL import Image
        except Exception:
            return []

        document = fitz.open(stream=content, filetype="pdf")
        texts: list[str] = []

        try:
            for page in document:
                pixmap = page.get_pixmap()
                mode = "RGBA" if pixmap.alpha else "RGB"
                image = Image.frombytes(mode, [pixmap.width, pixmap.height], pixmap.samples)
                texts.append(pytesseract.image_to_string(image).strip())
        finally:
            document.close()

        return texts

    def _build_sections(
        self,
        *,
        doc_id: str,
        page_profiles: list[PdfPageProfile],
        section_type: str,
    ) -> list[ParsedSection]:
        sections: list[ParsedSection] = []
        for profile in page_profiles:
            sections.append(
                ParsedSection(
                    section_id=f"{doc_id}-page-{profile.page_number}",
                    title=f"Page {profile.page_number}",
                    content=profile.text,
                    section_type=section_type,
                    page_start=profile.page_number,
                    page_end=profile.page_number,
                    metadata={"line_count": len(profile.non_empty_lines)},
                )
            )
        return sections

    def _build_page_blocks(
        self,
        *,
        doc_id: str,
        page_profiles: list[PdfPageProfile],
        include_tables: bool,
    ) -> list[ParsedPageBlock]:
        blocks: list[ParsedPageBlock] = []
        repeated_headers, repeated_footers = self._detect_repeated_marginal_lines(page_profiles)

        for profile in page_profiles:
            block_order = 0
            table_group_keys = {tuple(group) for group in profile.table_groups}
            text_groups = self._group_text_lines(profile.lines)

            for index, group in enumerate(text_groups):
                if not group:
                    continue

                group_key = tuple(group)
                if group_key in table_group_keys and not include_tables:
                    continue

                text = "\n".join(group).strip()
                if not text:
                    continue

                block_type = self._classify_group_block_type(
                    group=group,
                    group_index=index,
                    group_count=len(text_groups),
                    page_number=profile.page_number,
                    repeated_headers=repeated_headers,
                    repeated_footers=repeated_footers,
                    is_table_group=group_key in table_group_keys,
                )

                block_order += 1
                blocks.append(
                    ParsedPageBlock(
                        block_id=f"{doc_id}-page-{profile.page_number}-block-{block_order}",
                        block_type=block_type,
                        text=text,
                        page=profile.page_number,
                        order=block_order,
                        metadata={"line_count": len(group), "source": "heuristic"},
                    )
                )

        return blocks

    def _classify_group_block_type(
        self,
        *,
        group: list[str],
        group_index: int,
        group_count: int,
        page_number: int,
        repeated_headers: dict[int, str],
        repeated_footers: dict[int, str],
        is_table_group: bool,
    ) -> str:
        text = "\n".join(group).strip()
        first_line = group[0].strip()

        if page_number in repeated_headers and first_line == repeated_headers[page_number]:
            return "header"
        if page_number in repeated_footers and first_line == repeated_footers[page_number]:
            return "footer"
        if self._is_table_caption(text):
            return "table_caption"
        if self._is_figure_caption(text):
            return "figure_caption"
        if is_table_group:
            return "table"
        if self._looks_like_list_item(group):
            return "list_item"
        if self._looks_like_heading(group):
            return "heading"
        if group_index == group_count - 1 and self._looks_like_page_number(text):
            return "footer"
        return "paragraph"

    def _build_tables(
        self,
        *,
        doc_id: str,
        page_profiles: list[PdfPageProfile],
        page_blocks: list[ParsedPageBlock],
    ) -> list[ParsedTable]:
        block_lookup = {(block.page, block.text): block for block in page_blocks if block.block_type == "table"}
        caption_lookup = defaultdict(list)
        for block in page_blocks:
            if block.block_type == "table_caption":
                caption_lookup[block.page].append(block)

        tables: list[ParsedTable] = []
        table_index = 0

        for profile in page_profiles:
            for group in profile.table_groups:
                rows = [self._split_table_row(line) for line in group]
                rows = [row for row in rows if len(row) >= 2]
                if not rows:
                    continue

                table_index += 1
                normalized_rows = self._normalize_rows(rows)
                headers = normalized_rows[0]
                body_rows = normalized_rows[1:] if len(normalized_rows) > 1 else []
                markdown = self._table_to_markdown(normalized_rows)
                source_text = "\n".join(group).strip()
                source_block = block_lookup.get((profile.page_number, source_text))

                tables.append(
                    ParsedTable(
                        table_id=f"{doc_id}-table-{table_index}",
                        table_type="pdf_table",
                        title=caption_lookup[profile.page_number][0].text if caption_lookup[profile.page_number] else None,
                        raw_markdown=markdown,
                        page=profile.page_number,
                        headers=headers,
                        rows=body_rows,
                        source_block_id=source_block.block_id if source_block else None,
                        metadata={
                            "row_count": len(normalized_rows),
                            "column_count": len(headers),
                            "parse_mode": "heuristic",
                        },
                    )
                )

        return tables

    def _finalize_document(
        self,
        *,
        parsed_document: ParsedDocument,
        page_profiles: list[PdfPageProfile],
        effective_page_profiles: list[PdfPageProfile],
        route: str,
    ) -> ParsedDocument:
        total_pages = len(page_profiles)
        scoped_page_profiles = effective_page_profiles or page_profiles
        parsed_page_count = len(scoped_page_profiles)
        parsed_page_range = self._resolve_parsed_page_range(scoped_page_profiles)
        empty_page_count = sum(1 for profile in scoped_page_profiles if not profile.has_text)
        text_coverage = 0.0 if parsed_page_count == 0 else (parsed_page_count - empty_page_count) / parsed_page_count

        if route in {"ocr_pdf", "mineru_pdf"} and parsed_page_count:
            parsed_pages = {
                block.page
                for block in parsed_document.page_blocks
                if block.page is not None and block.text.strip()
            }
            parsed_output_coverage = len(parsed_pages) / parsed_page_count
            if parsed_output_coverage > text_coverage:
                text_coverage = min(parsed_output_coverage, 1.0)
                empty_page_count = max(parsed_page_count - len(parsed_pages), 0)

        issues = list(parsed_document.issues)
        if empty_page_count:
            issues.append(
                ParseIssue(
                    code="empty_pages_detected",
                    message=f"Detected {empty_page_count} page(s) without extractable text.",
                    severity="warning",
                    details={"empty_page_count": empty_page_count},
                )
            )

        if text_coverage < 0.5:
            issues.append(
                ParseIssue(
                    code="low_text_coverage",
                    message="PDF text coverage is low; scanned or image-based content may require OCR.",
                    severity="warning",
                    details={"text_coverage": text_coverage},
                )
            )

        if route != "table_pdf" and self._should_use_table_route(scoped_page_profiles) and not parsed_document.tables:
            issues.append(
                ParseIssue(
                    code="table_content_detected",
                    message="Table-like page structure detected, but the selected route did not extract tables.",
                    severity="info",
                )
            )

        confidence = self._estimate_confidence(
            route=route,
            text_coverage=text_coverage,
            table_count=len(parsed_document.tables),
            issue_count=len(issues),
        )

        parsed_document.issues = issues
        parsed_document.quality = ParseQualityReport(
            route=route,
            confidence=confidence,
            text_coverage=text_coverage,
            empty_page_count=empty_page_count,
            table_count=len(parsed_document.tables),
            issue_count=len(issues),
        )
        parsed_document.metadata = with_parse_metadata(
            parsed_document.metadata,
            parse_backend=parsed_document.metadata.parse_backend or "unknown",
            parse_route=route,
            parse_strategy="dify-style-router",
            page_count=total_pages,
            parsed_page_range=parsed_page_range,
            parsed_page_count=parsed_page_count,
            content_quality_score=confidence,
        )
        return parsed_document

    def _estimate_confidence(self, *, route: str, text_coverage: float, table_count: int, issue_count: int) -> float:
        base = {
            "native_pdf": 0.78,
            "table_pdf": 0.84,
            "ocr_pdf": 0.66,
            "mineru_pdf": 0.9,
        }.get(route, 0.7)

        confidence = base
        confidence += min(table_count, 3) * 0.02
        confidence += max(text_coverage - 0.5, 0) * 0.1
        confidence -= min(issue_count, 4) * 0.06
        return round(max(0.2, min(confidence, 0.98)), 3)

    def _group_text_lines(self, lines: list[str]) -> list[list[str]]:
        groups: list[list[str]] = []
        current_group: list[str] = []
        current_kind: str | None = None

        for raw_line in lines:
            line = raw_line.rstrip()
            if not line.strip():
                if current_group:
                    groups.append(current_group)
                    current_group = []
                    current_kind = None
                continue

            cleaned = line.strip()
            line_kind = self._line_kind(cleaned)

            if current_group and self._should_split_group(previous_kind=current_kind, current_kind=line_kind):
                groups.append(current_group)
                current_group = []

            current_group.append(cleaned)
            current_kind = line_kind

        if current_group:
            groups.append(current_group)

        return groups

    def _line_kind(self, line: str) -> str:
        if self._is_table_caption(line):
            return "table_caption"
        if self._is_figure_caption(line):
            return "figure_caption"
        if self._looks_like_page_number(line):
            return "footer"
        if self._looks_like_list_item([line]):
            return "list_item"
        if self._is_table_line(line):
            return "table"
        if self._looks_like_heading([line]):
            return "heading"
        return "paragraph"

    def _should_split_group(self, *, previous_kind: str | None, current_kind: str) -> bool:
        singleton_kinds = {"table_caption", "figure_caption", "list_item", "footer", "heading"}
        if previous_kind is None:
            return False
        if current_kind in singleton_kinds or previous_kind in singleton_kinds:
            return True
        if current_kind != previous_kind and "table" in {current_kind, previous_kind}:
            return True
        return False

    def _detect_table_groups(self, lines: list[str]) -> list[list[str]]:
        candidate_groups: list[list[str]] = []
        current_group: list[str] = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                if len(current_group) >= 2:
                    candidate_groups.append(current_group)
                current_group = []
                continue

            if self._is_table_caption(line) or self._is_figure_caption(line):
                if len(current_group) >= 2:
                    candidate_groups.append(current_group)
                current_group = []
                continue

            if self._is_table_line(line):
                current_group.append(line)
            else:
                if len(current_group) >= 2:
                    candidate_groups.append(current_group)
                current_group = []

        if len(current_group) >= 2:
            candidate_groups.append(current_group)

        return candidate_groups

    def _detect_repeated_marginal_lines(self, page_profiles: list[PdfPageProfile]) -> tuple[dict[int, str], dict[int, str]]:
        normalized_header_counter: Counter[str] = Counter()
        normalized_footer_counter: Counter[str] = Counter()
        top_lines: dict[int, str] = {}
        bottom_lines: dict[int, str] = {}

        for profile in page_profiles:
            non_empty_lines = profile.non_empty_lines
            if not non_empty_lines:
                continue
            top_lines[profile.page_number] = non_empty_lines[0]
            bottom_lines[profile.page_number] = non_empty_lines[-1]
            normalized_header_counter[self._normalize_marginal_line(non_empty_lines[0])] += 1
            normalized_footer_counter[self._normalize_marginal_line(non_empty_lines[-1])] += 1

        repeated_headers = {
            page: line
            for page, line in top_lines.items()
            if normalized_header_counter[self._normalize_marginal_line(line)] >= 2 and len(line) <= 80
        }
        repeated_footers = {
            page: line
            for page, line in bottom_lines.items()
            if normalized_footer_counter[self._normalize_marginal_line(line)] >= 2 and len(line) <= 80
        }
        return repeated_headers, repeated_footers

    def _normalize_marginal_line(self, line: str) -> str:
        normalized = re.sub(r"\d+", "#", line.strip().lower())
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    _MONEY_TOKEN_RE = re.compile(
        r"\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?"
        r"|\(?-?\d+\.\d{2}\)?"
        r"|\(?-?\d{4,}\.?\d*\)?"
    )

    def _is_table_line(self, line: str) -> bool:
        if "|" in line:
            return len([part for part in line.split("|") if part.strip()]) >= 2

        if "\t" in line:
            return len([part for part in line.split("\t") if part.strip()]) >= 2

        # A-share statement rows are often single-spaced:
        # "货币资金 1,607,489,512.00 1,204,846,130.00"
        chinese_financial = self._split_chinese_financial_row(line)
        if chinese_financial is not None and len(chinese_financial) >= 2:
            return True

        if re.search(r"(项目|item).{0,12}(20\d{2}|19\d{2})", line, flags=re.IGNORECASE):
            return True

        parts = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]
        if len(parts) < 2:
            return False

        numeric_parts = sum(1 for part in parts if re.search(r"\d", part))
        if numeric_parts >= 1 or len(parts) >= 3:
            return True

        if len(parts) == 2 and all(re.search(r"[A-Za-z\u4e00-\u9fff]", part) for part in parts):
            return True

        return False

    def _split_chinese_financial_row(self, line: str) -> list[str] | None:
        cleaned = line.strip()
        if not cleaned or not re.search(r"[\u4e00-\u9fff]", cleaned):
            return None

        money_matches = list(self._MONEY_TOKEN_RE.finditer(cleaned))
        if not money_matches:
            # Header-like: 项目 2021年12月31日 2020年12月31日
            if re.search(r"(项目|item).{0,8}(20\d{2}|19\d{2})", cleaned, flags=re.IGNORECASE):
                parts = [part for part in re.split(r"\s+", cleaned) if part]
                return parts if len(parts) >= 2 else None
            return None

        first_money = money_matches[0]
        label = cleaned[: first_money.start()].strip()
        if not label or len(label) > 40:
            return None

        values = [match.group(0) for match in money_matches]
        # Require at least one comma-formatted amount or two numeric columns.
        has_comma_amount = any("," in value for value in values)
        if not has_comma_amount and len(values) < 2:
            return None
        return [label, *values]

    def _split_table_row(self, line: str) -> list[str]:
        if "|" in line:
            parts = [part.strip() for part in line.split("|") if part.strip()]
        elif "\t" in line:
            parts = [part.strip() for part in line.split("\t") if part.strip()]
        else:
            chinese_financial = self._split_chinese_financial_row(line)
            if chinese_financial is not None:
                parts = chinese_financial
            else:
                parts = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]
        return parts

    def _normalize_rows(self, rows: list[list[str]]) -> list[list[str]]:
        if not rows:
            return []
        width = max(len(row) for row in rows)
        return [row + [""] * (width - len(row)) for row in rows]

    def _table_to_markdown(self, rows: list[list[str]]) -> str:
        if not rows or not rows[0]:
            return ""

        header = rows[0]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * len(header)) + " |",
        ]
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def _looks_like_heading(self, group: list[str]) -> bool:
        if len(group) != 1:
            return False

        line = group[0].strip()
        if not line or len(line) > 90:
            return False
        if line.endswith((".", "。", ";", "；", ":", "：")):
            return False
        if self._is_table_line(line):
            return False

        cjk_count = sum(1 for char in line if "\u4e00" <= char <= "\u9fff")
        cjk_ratio = cjk_count / max(len(line), 1)
        if cjk_ratio >= 0.25:
            return bool(
                re.match(
                    r"^(第[一二三四五六七八九十百千零〇\d]+[章节篇部]"
                    r"|[（(]?[一二三四五六七八九十]+[、.．)]"
                    r"|\d+[、.．]\s*\S+"
                    r"|[一二三四五六七八九十]+、\s*\S+"
                    r"|附录|重要提示、目录和释义)",
                    line,
                )
                or re.search(
                    r"(管理层讨论与分析|合并资产负债表|合并利润表|合并现金流量表"
                    r"|公司简介和主要财务指标|公司治理|财务报告)",
                    line,
                )
            )

        latin_chars = sum(1 for char in line if ("A" <= char <= "Z") or ("a" <= char <= "z"))
        if latin_chars == 0:
            return False

        alpha_ratio = latin_chars / max(len(line), 1)
        title_case = line == line.title() and alpha_ratio > 0.4
        upper_case = line == line.upper() and alpha_ratio > 0.5
        numbered_heading = bool(re.match(r"^(\d+(\.\d+)*)\s+\S+", line))
        return title_case or upper_case or numbered_heading

    def _looks_like_list_item(self, group: list[str]) -> bool:
        if len(group) != 1:
            return False
        return bool(re.match(r"^([-*•●]|(\d+[\.\)]))\s+\S+", group[0].strip()))

    def _is_table_caption(self, text: str) -> bool:
        return bool(re.match(r"^(table|表)\s*[\d一二三四五六七八九十]+[\s:：.\-—_]*\S+", text.strip(), re.IGNORECASE))

    def _is_figure_caption(self, text: str) -> bool:
        return bool(re.match(r"^(figure|fig\.?|图)\s*[\d一二三四五六七八九十]+[\s:：.\-—_]*\S+", text.strip(), re.IGNORECASE))

    def _looks_like_page_number(self, text: str) -> bool:
        normalized = text.strip().lower()
        return bool(re.match(r"^(page\s+\d+|\d+/\d+|\d+)$", normalized))
