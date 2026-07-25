# Financial document invariants

## Provenance

Structured facts (`FinancialMetricFact`, note facts, statement metrics) used for research or company APIs should retain source linkage when available:

- `source_table_id` / table title
- page range or section
- `provenance` dict fields already on the model

Do not silently drop provenance when refactoring mappers.

## Status machine

Only use `DocumentProcessingStatus` values. Transitions must pass `ensure_transition` in `state_machine.py`. Terminal `completed` must not be mutated without an explicit product decision.

## Stable identifiers

Treat these as public contracts unless the user asks to break them:

- PDF `parse_route` names: `native_pdf`, `ocr_pdf`, `table_pdf`, `mineru_pdf`
- `metric_key` strings consumed by APIs and golden files
- Vector collection naming / embedding dimensionality pairing
- Knowledge graph node and relationship type names

## Grounding

Research answers should prefer hybrid evidence (vector hits + metrics + graph paths). Flag changes that make the LLM the sole source of numeric claims when structured metrics exist.

## Golden data

Intentional extraction behavior changes should update `data/golden/` expectations and mention schema benchmark / parser tests.
