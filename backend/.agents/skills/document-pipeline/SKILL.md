---
name: document-pipeline
description: Guides work on the Claude Copilot document AI pipeline — status machine, parse→segment→tables→structure→schema→chunk→index→graph stages, and where to extend parsers or post-processors. Use when editing feature_pipeline, DocumentPipelineService, document status transitions, upload/processing flow, or adding a pipeline stage.
---

# Document Pipeline

## Scope

Primary code: `app/pipeline/feature_pipeline/`.

Orchestrator: `pipeline_service.py`  
Status rules: `state_machine.py`  
Domain models: `src/claude_copilot/schemas/document.py`

## Stage order

Always respect this order when changing or debugging the pipeline:

1. **Parse** — `parser/` via `ParserRouter` / `ExtractProcessor`
2. **Segment** — `segmentation/` (MD&A, risk, notes, …)
3. **Table intelligence** — `table_intelligence/`
4. **Structure reconstruction** — `structure_reconstruction/`
5. **Financial schema mapping** — `schema_mapping/` → `FinancialSchema`
6. **Chunk** — `chunking/` → `DocumentSegment` list
7. **Index** — `indexing/` → segment repo + vector store
8. **Knowledge graph** — `app/core/kg/` (after schema is available)

Do **not** skip schema mapping when downstream financial metrics, SQL facts, or graph nodes depend on structured output.

## Status machine

Allowed transitions (see `ALLOWED_TRANSITIONS`):

```text
waiting → parsing → cleaning? → chunking → indexing → completed
         ↘ failed / paused (with resume paths)
failed → waiting | parsing
completed → (terminal)
```

Use `ensure_transition(current, target)` — never invent new status strings outside `DocumentProcessingStatus`.

## Extension checklist

When adding a capability:

- [ ] New parser? Register in `parser/` router / extract processor; cover extension + content-type.
- [ ] New post-parse step? Insert in `pipeline_service` in the correct stage; keep side effects idempotent where possible.
- [ ] Persist new fields on `ParsedDocument` / `DocumentMetadata` / `FinancialSchema` in `src/claude_copilot/schemas/`.
- [ ] Update tests in `tests/test_parsers.py` or focused pipeline tests; use `tmp_path` for storage.
- [ ] If indexing/KG inputs change, note whether `scripts/backfill_*.py` must be re-run.

## Debugging

- Inspect intermediate state: `scripts/inspect_doc_ai_state.py`
- Multi-format smoke: `scripts/run_multi_format_doc_ai_smoke.py`
- Failed docs: check `DocumentRecord.error_message` and `ParsedDocument.issues` / `quality`

## Related skills

- PDF route selection → `pdf-routing`
- `FinancialSchema` / tables → `financial-schema-mapping`
- Vectors / retrieval → `hybrid-retrieval`
- Graph build → `knowledge-graph`
