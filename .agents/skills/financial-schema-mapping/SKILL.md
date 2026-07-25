---
name: financial-schema-mapping
description: Guides mapping parsed financial tables and sections into FinancialSchema — statements, notes, metric facts, provenance, and golden benchmarks. Use when editing schema_mapping, table_intelligence, FinancialSchema models, metric keys, or schema accuracy for annual reports / 10-K-like docs.
---

# Financial Schema Mapping

## Scope

- Models: `src/claude_copilot/schemas/document.py` (`FinancialSchema`, statements, notes, metric/note facts)
- Mapping: `app/pipeline/feature_pipeline/schema_mapping/`
- Tables: `app/pipeline/feature_pipeline/table_intelligence/`
- Segmentation cues: `app/pipeline/feature_pipeline/segmentation/`
- Golden / eval: `data/golden/`, `app/pipeline/feature_pipeline/evaluation/`
- Benchmark: `scripts/run_schema_benchmark.py`

## Target shape

`FinancialSchema` aggregates:

- `statements` — income / balance / cash-flow style tables → `FinancialStatementSchema`
- `notes` — footnote tables → `FinancialNoteSchema` + `note_facts`
- `metric_facts` — flat facts with `metric_key`, `period`, `value`, **provenance**
- `semantic_sections` — MD&A, risk, etc.
- `metrics_index` — convenience period→value index
- `company` / `year` / `reporting_periods`

## Working rules

1. **Provenance is mandatory** for facts used in research/SQL — keep `source_table_id`, page range, section when available.
2. Prefer stable `metric_key` naming; do not rename keys casually (breaks golden data and company APIs).
3. Classify tables before mapping (statement vs note vs other); wrong class pollutes metrics.
4. Preserve units/currency/period headers on statement schemas.
5. Bilingual labels (EN/ZH) may appear in headers and cues — match existing patterns.
6. Update or extend golden expectations under `data/golden/` when intentionally changing extraction semantics.

## Change checklist

- [ ] Adjust `table_intelligence` classification if statement/note detection is wrong
- [ ] Map into existing schema models before inventing parallel dict shapes
- [ ] Keep `FinancialMetricFact.provenance` / statement provenance populated
- [ ] Add/adjust tests near `tests/test_parsers.py` post-processing helpers
- [ ] Run `uv run python scripts/run_schema_benchmark.py` when accuracy is in scope

## Downstream consumers

Schema feeds:

- Chunk metadata / indexing context
- `app/core/db` financial data repository / company metrics APIs
- Knowledge graph builder (`app/core/kg/`)
- Research retrieval (structured + hybrid routes)

Breaking schema fields requires coordinated updates across these layers.
