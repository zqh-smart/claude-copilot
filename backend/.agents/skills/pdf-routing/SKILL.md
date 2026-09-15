---
name: pdf-routing
description: Guides PDF parse route selection among native_pdf, ocr_pdf, table_pdf, and mineru_pdf — heuristics, optional extras, quality reports, and tests. Use when editing PdfDocumentParser, PDF_PARSER_BACKEND_PRIORITY, MinerU/OCR deps, or diagnosing bad PDF extractions text/tables.
---

# PDF Routing

## Scope

Code: `app/pipeline/feature_pipeline/parser/pdf_parser.py`  
Config: `PDF_PARSER_BACKEND_PRIORITY` in `app/core/config.py` / `.env`  
Extras: `pdf_ocr`, `pdf_mineru` in `pyproject.toml`

## Routes

| Route | When | Needs |
|-------|------|--------|
| `mineru_pdf` | Prefer rich layout / complex annual reports when MinerU is installed | `uv sync --extra pdf_mineru` |
| `table_pdf` | Heavy tabular layout heuristics (many line/table groups) | base deps |
| `native_pdf` | Text-layer PDFs with usable `pypdf` extraction | base deps (`pypdf`) |
| `ocr_pdf` | Low text coverage / scan-like pages | `uv sync --extra pdf_ocr` (+ system Tesseract) |

Default priority (config): `mineru_pdf,table_pdf,native_pdf,ocr_pdf`.

Selection walks the priority list after building per-page profiles (text coverage, table heuristics). Result metadata should set:

- `metadata.parse_route`
- `metadata.parse_backend` / strategy fields as implemented
- `ParsedDocument.quality` (`ParseQualityReport`: route, confidence, text_coverage, issues)

## Working rules

1. Prefer fixing route selection / quality signals over hardcoding a single backend for all PDFs.
2. Keep route names stable — they appear in tests, reports, and metadata.
3. Optional backends must degrade gracefully when extras are missing (skip route, continue priority list).
4. Preserve bilingual financial cue handling already present in parsers.

## Testing

```bash
uv run pytest tests/test_parsers.py -k pdf -q
uv run pytest tests/test_parsers.py -k mineru -q
```

Force a route in unit tests via `PdfDocumentParser(backend_priority=[...])` when available.

Debug helpers:

- `scripts/debug_mineru_output.py`
- `scripts/run_real_pdf_parse.py`

## Anti-patterns

- Assuming MinerU is always installed in CI/dev
- Dropping `ParseIssue` / quality reporting when changing extractors
- Changing default priority without updating README / AGENTS.md / tests
