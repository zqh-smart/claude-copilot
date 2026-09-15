# Document Parsing & Hybrid Retrieval Optimization

## 1. Scope and objective

This track covers only the coupled path below:

```text
PDF/document input
  -> parse routing
  -> cleaning / segmentation / table reconstruction
  -> financial schema + provenance
  -> retrieval-aware chunks
  -> Qdrant / SQL / knowledge graph
  -> query routing / fusion / reranking
  -> grounded evidence
```

Agent orchestration, frontend work and alert delivery are outside this track.

The objective is not merely to return results. A change is complete only when its own frozen
evaluation passes and the existing parsing and retrieval gates do not regress.

## 2. Verified baseline (2026-08-02)

### Document parsing

| Metric | Current verified value | Non-regression rule |
|---|---:|---:|
| `core_metric_exact_match` | 1.0 | must remain 1.0 |
| `source_grounding_rate` | 1.0 | must remain 1.0 |
| `source_table_grounding_rate` | 1.0 | must remain >= 0.995 |
| `implausible_period_ratio` | 0.0 | must remain 0.0 |
| `tiny_segment_ratio` | about 0.01 | must remain <= 0.02 |
| `duplicate_block_ratio` | about 0.10 | classify before removal; many repeats are valid table structure |

### Hybrid retrieval

The current retrieval-only gate passes 18/18 questions over three Serving-ingested annual
reports. Actual route combinations are:

| Route combination | Cases |
|---|---:|
| SQL | 9 |
| Vector | 3 |
| Vector + SQL | 1 |
| Vector + graph | 3 |
| Graph | 2 |

This proves the three channels are wired and useful, but it does not yet prove ranking quality
over a broad production distribution. The current golden set is small and most semantic checks
use section/keyword expectations rather than explicit relevant segment IDs.

## 3. Evaluation contract

### 3.1 Parsing gates

- Text PDFs: text coverage and parser confidence must not regress.
- Scanned/rotated/low-quality PDFs: track CER by slice and route/fallback correctness.
- Tables: track TEDS/cell accuracy, period and unit alignment, and cross-page header continuity.
- Sections: track boundary precision/recall/F1 for MD&A, risk, statements and notes.
- Facts: core metric exact match, period plausibility and provenance remain hard gates.
- Cleaning: report header/footer residue and near-duplicate blocks separately.

### 3.2 Retrieval gates

Required report metrics:

- Route accuracy and per-channel result counts.
- Structured metric exact match.
- Graph relation/path correctness.
- `hit_rate@5`, reciprocal rank and `nDCG@5` for semantically evaluable cases.
- Failure categories: routing, structured metric, semantic recall, section metadata, graph path.
- Channel-combination counts and route-coverage ablation.
- Retrieval latency p50/p95 once enough samples are available.

Until golden cases contain `expect_relevant_segment_ids`, ranking metrics derived from expected
section types and keywords must be labelled `semantic_proxy`. They are useful for regression but
must not be reported as strict corpus-level Recall@K.

Target thresholds after explicit relevance labels are added:

| Metric | Target |
|---|---:|
| route accuracy | >= 0.98 |
| Recall@5 | >= 0.95 |
| MRR@10 | >= 0.90 |
| nDCG@10 | >= 0.90 |
| structured metric exact match | 1.0 |
| graph path precision/recall | >= 0.95 |
| no-answer abstention accuracy | >= 0.95 |
| retrieval p95 | <= 3 seconds |

## 4. Ordered optimization backlog

### P0 - Make evaluation diagnostic

1. ~~Add ranking proxy metrics, channel coverage/ablation and failure classification~~ ✅
2. Expand the frozen corpus to 10-20 documents and 80-120 questions — **in progress**
   (`data/golden/joint_retrieval_benchmark/manifest.json`; 3 ready + draft slots).
3. Explicit fingerprints + hard negatives on core semantic cases ✅; more labels pending.
4. Cross-year / cross-company / abstain cases added under `benchmark_cases` (soft suite).

**Runner:** `python scripts/run_joint_retrieval_benchmark.py`  
Reports: `data/reports/joint_retrieval_benchmark/latest_joint_retrieval_benchmark.json`  
Metrics now include `recall_at_5`, `mrr_at_10`, `ndcg_at_10`, abstention accuracy, latency
p50/p95, and **true** channel ablation via `routes_override` (vector/sql/graph combinations).

`retrieval_cases` remain the hard 18/18 L3 gate. New difficulty lives in `benchmark_cases`
so expansion can stay red while labelling without breaking acceptance.

Completion gate: evaluator unit tests green; 18/18 gate green; joint report emits @10 + ablation.

### P1 - Reduce parser noise before tuning retrieval

1. Split repeated blocks into structural repeats and harmful narrative duplicates before removal.
2. Improve cross-page table header, unit and period inheritance.
3. Record per-page route/backend/confidence/fallback reasons for mixed PDFs.
4. Add section-boundary labels rather than only section-presence checks.

Completion gate: harmful narrative duplicate ratio is measured separately and reduced without
deleting valid repeated table headers/units/financial rows; table grounding improves toward
0.995, and core metric/grounding/period gates do not regress.

### P2 - Retrieval-aware chunking

Maintain three complementary representations:

- narrative chunks for MD&A, business and risk text;
- table/metric chunks containing metric, period, unit, row/column and table provenance;
- parent section chunks for contextual expansion after a small child chunk matches.

Every indexed segment should preserve document/company/year/type, section, page range, table ID,
parent section ID and provenance where applicable.

Completion gate: backfill to a new BGE-M3-compatible collection, never mix hash and real vectors,
then pass L2, L3 and ranking gates.

### P3 - Query-aware fusion and reranking

- Exact amount questions: SQL is authoritative; vector evidence is optional context.
- Causal/trend questions: vector + SQL, with period and metric consistency constraints.
- Risk questions: vector evidence and graph relations validate each other.
- Relationship questions: graph first, vector evidence used for grounding.
- Deduplicate same-page/same-table/near-identical candidates before final top-k.
- Tune fusion weights by route slice, not with one global weight.

Completion gate: measured improvement on hard negatives and ranking metrics with no regression in
exact metrics, source grounding, graph paths or latency budget.

## 5. Failure feedback loop

| Failure | Owning stage |
|---|---|
| Source text missing | parser/OCR |
| Period, unit or table cell wrong | table intelligence/schema mapping |
| Wrong or fragmented section | segmentation/chunking |
| Correct segment absent from candidates | embedding/query expansion |
| Correct segment retrieved but ranked low | fusion/reranker |
| Exact number inconsistent | schema/SQL facts |
| Wrong company/risk relationship | knowledge graph |
| Unsupported answer from weak evidence | no-answer/grounding gate |

Each optimization report must identify the owning stage, before/after metrics, artifacts written,
and the exact regression commands executed.

## 6. Standard verification order

```powershell
uv run pytest tests/test_retrieval_eval_common.py tests/core/rag -q
uv run python scripts/run_stage_eval.py --compare-baseline
uv run python scripts/run_l4_research_eval.py --profile all --retrieval-only
uv run pytest -q
```

After any chunking or embedding change:

```powershell
uv run python scripts/backfill_qdrant.py
```

Do not trust retrieval results from a collection built with a different embedding model,
dimension or chunk contract.

## 7. Iteration log

### 2026-08-02 - Diagnostic evaluator and redundant-evidence removal

Changes:

- Retrieval reports now include per-case ranking diagnostics, route combinations,
  route-coverage ablation and failure categories.
- Ranking based on section/keyword expectations is explicitly labelled `semantic_proxy`;
  strict Recall is deferred until golden cases contain relevant segment IDs.
- Retrieval candidates are deduplicated before reranking when their normalized text is identical,
  or when a long candidate (at least 120 characters) is wholly contained in another candidate.
- Parser blocks and stored chunks are not deleted, preserving table structure and provenance.
- The stage scorecard separates short structural repeats from long narrative duplicate
  candidates while retaining the original aggregate ratio for compatibility.

Measured result:

| Check | Result |
|---|---:|
| retrieval-only gate | 18/18 |
| proxy hit rate@5 | 1.0 |
| proxy MRR@5 | 1.0 |
| proxy nDCG@5 | 0.9275 |
| all-channel route coverage | 18/18 |
| retrieval failure categories | none |
| focused tests | 32 passed |
| full tests | 268 passed, 1 skipped |

On the Tianhua MD&A query, two overlapping candidates previously had pair similarity about
0.8002 and consumed two top-five positions. After containment deduplication, the maximum pair
similarity in the returned top five was 0.048 and five distinct evidence items remained.

The stage scorecard still passes Serving gates and preserves `core_metric_exact_match=1.0`,
`source_grounding_rate=1.0` and `implausible_period_ratio=0.0`. Its soft comparison remains
`mixed`: one TOC-like block remains, table grounding is 0.9848 versus the older 0.987 baseline,
and tiny segment ratio is 0.0124 versus 0.0097. These are tracked as parser/chunking follow-ups;
they were not modified by this retrieval-only change.

The new duplicate split confirms that the aggregate 0.0999 ratio should not be used as a direct
deletion target:

| Duplicate slice | Ratio |
|---|---:|
| short structural repeats | 0.0993 |
| long narrative duplicate candidates | 0.0006 |

The dominant repeats are table headers, units, checkbox disclosures and recurring financial row
labels. The next parser optimization should therefore target the remaining TOC-like block and
table grounding, while retrieval handles redundant overlapping evidence without destroying source
structure.

### 2026-08-02 - TOC cleanup and exact fact provenance

Problem and ownership:

- Cleaning left one 1,293-character multi-line contents block because the prior TOC heuristic
  handled only single lines or short text. This belonged to document cleaning, not retrieval.
- One correctly extracted 2021 revenue fact was bound to the wrong member of four merged income
  statement tables. The provenance resolver reused a 0.1% numeric tolerance intended for broader
  metric comparison, so `932,420,978` was considered equal to `931,944,638`. This belonged to
  schema mapping.

Changes:

- A multi-line TOC is removed only when it starts with an exact TOC title, has at least three
  non-empty lines, and at least two following lines match existing TOC-entry rules. Narrative
  mentions such as “产品目录调整” remain untouched.
- Metric provenance now uses exact decimal equality when selecting a source table from merged
  statements. The existing tolerant comparison remains unchanged outside source binding.
- Source-grounding diagnostics now retain table-specific failures even when the value exists in
  the global document corpus, including the bound `source_table_id` and a precise failure reason.

Measured result:

| Check | Before | After |
|---|---:|---:|
| `toc_like_remaining` | 1 | 0 |
| `source_table_grounding_rate` | 0.9848 | 1.0 |
| `core_metric_exact_match` | 1.0 | 1.0 |
| `source_grounding_rate` | 1.0 | 1.0 |
| `implausible_period_ratio` | 0.0 | 0.0 |
| retrieval-only gate | 18/18 | 18/18 |
| schema benchmark | not run in iteration | 10 checks, 0 failures |
| full tests | 268 passed, 1 skipped | 271 passed, 1 skipped |

The schema benchmark completed in 287.69 seconds and reported full statement, note, metric-fact
and note-fact provenance coverage. MinerU logged a PDF classification warning and then completed
the 21-page pipeline successfully; the benchmark itself had zero failures.

The stage comparison is still `mixed`, not fully positive. `tiny_segment_ratio=0.0124` remains
above the older 0.0097 baseline, although it is below the 0.02 acceptance ceiling. Parser
throughput also varied from the saved baseline (`29.964` to `14.047` pages/second), while the
separate MinerU benchmark ran at approximately `0.079` page/second on its OCR-heavy route. These
runtime numbers require repeated warm/cold measurements before attributing a code regression.

Next optimization order:

1. Add explicit relevant segment IDs and hard negatives to the retrieval golden set, replacing
   semantic-proxy ranking with strict Recall/MRR/nDCG on labelled cases.
2. Diagnose tiny segments by section type, parser route and content class before changing chunk
   thresholds; merge only low-information fragments whose parent/provenance can be preserved.
3. Add per-stage timing/progress to the schema benchmark so slow parser/model initialization is
   distinguishable from cleaning, mapping and indexing latency.

### 2026-08-02 - Stable explicit relevance and hard-negative baseline

Problem:

- Stored `segment_id` values contain a random ingestion document UUID. Golden labels written
  against those IDs would silently become invalid after re-ingestion.
- The prior ranking score covered four semantic cases but all four used section/keyword proxies.
  It could not distinguish a directly useful paragraph from a cross-reference or a table with a
  conflicting reporting scope.

Changes:

- Every newly chunked segment now carries `metadata.segment_fingerprint`, a SHA-256 digest of
  normalized, case-folded content. It remains stable across document UUID changes and deliberately
  changes when parsing or chunk content changes.
- Retrieval reports include top-five hit references: segment ID, fingerprint, score, section,
  page range and a bounded content preview. These fields make manual labels auditable.
- The three Chinese annual-report golden files now contain manually reviewed relevant
  fingerprints for four semantic/hybrid cases and explicit hard-negative fingerprints.
- Ranking diagnostics now report explicit-vs-proxy case counts and
  `hard_negative_rate_at_5`. Phase-H expectation hashes were refreshed after the intentional
  golden-data change; its frozen-input validation remains green.

Measured explicit-ranking baseline:

| Metric | Result |
|---|---:|
| evaluated ranking cases | 4 |
| explicit relevance cases | 4 |
| semantic proxy cases | 0 |
| Hit@5 | 1.0 |
| MRR@5 | 1.0 |
| nDCG@5 | 0.947 |
| hard-negative rate@5 | 1.0 |
| complete retrieval gate | 18/18 |
| full tests | 273 passed, 1 skipped |

The hard-negative rate is intentionally reported as a failing-quality signal rather than hidden
behind the 18/18 route/content gate. Current examples include:

- short “see section X” references that repeat query terms but provide no evidence;
- corporate-governance paragraphs incorrectly competing with MD&A evidence;
- a consolidated revenue table (`932,420,978`) competing with the structured authoritative fact
  selected for the query (`931,944,638`), demonstrating a reporting-scope conflict.

Serving re-ingest note: `run_serving_ingest_eval.py --expectations ...` does not infer the matching
PDF from that expectations file. A first Jucan attempt therefore ingested the default ZNZ PDF and
correctly failed at 0.4 when compared against Jucan facts. The valid Jucan and Tianhua re-ingests
were rerun with explicit `--pdf-path` and both passed at 1.0. Future automation should use the
Phase-H manifest source path or require `--pdf-path` for non-default expectations.

Next ranking optimization should first suppress evidence-free cross-references and repair section
metadata before tuning global fusion weights. Success means lower hard-negative@5 while preserving
the four explicit Hit/MRR/nDCG cases, the 18/18 gate and structured-source grounding.

Follow-up candidate filtering:

- Tiny-segment inspection found 12/966 ZNZ, 9/1059 Jucan and 9/1172 Tianhua segments below 40
  characters. Most were headings, glossary tails, table rows or cross-page fragments; only two
  were pure cross-references. A global minimum-length deletion would therefore remove legitimate
  financial structure and was rejected.
- Retrieval now drops only candidates of at most 80 compact characters that point to another
  report section, contain no percentage evidence, and otherwise provide no direct evidence.
  Stored segments and parser output remain unchanged.
- After filtering and manually labelling newly exposed audit-procedure negatives, explicit
  `nDCG@5` improved from `0.947` to `0.9714`; hard-negative@5 fell from `1.0` to `0.75`.
  Hit@5 and MRR@5 remained `1.0`, the complete retrieval gate remained 18/18, and the full suite
  passed 273 tests with one skip.

The remaining hard negatives are substantive rather than trivial: reporting-scope conflict,
governance text carrying incorrect MD&A metadata, and audit-procedure passages. The next change
should improve section ownership/metadata and query-aware reranking; it should not broaden the
short-reference filter without new labels.

### 2026-08-03 - Joint benchmark baseline (P0)

Command:

```powershell
.\.venv\Scripts\python.exe scripts/run_joint_retrieval_benchmark.py
# faster recheck after labelling:
.\.venv\Scripts\python.exe scripts/run_joint_retrieval_benchmark.py --no-ablation
```

Report: `data/reports/joint_retrieval_benchmark/latest_joint_retrieval_benchmark.json`

Corpus after first expansion + labelling pass:

| Suite | Cases | Passed |
|---|---:|---:|
| L3 gate (`retrieval_cases`) | 18 | **18** |
| Benchmark (`benchmark_cases`) | 16 | 13 |
| Explicit fingerprint ranking cases | 11 | — |

Ranking (explicit labels only):

| Metric | Value | Target |
|---|---:|---:|
| Hit@5 | 1.0 | — |
| Recall@5 | 0.8106 | ≥ 0.95 |
| MRR@10 | 0.9545 | ≥ 0.90 |
| nDCG@10 | 0.9002 | ≥ 0.90 |
| hard-negative@5 | **0.8182** | ↓ |
| hard-negative@10 | 0.9091 | ↓ |

True channel ablation (forced `routes_override`, full run):

| Channel | pass_rate |
|---|---:|
| all_hybrid | 0.794 |
| vector+sql | 0.706 |
| sql_only | 0.441 |
| vector_only / vector+graph | 0.353 |
| graph_only | 0.176 |

Remaining intentional red cases (3): cross-company questions still return pinned-doc SQL metrics
(`abstention` failure). Do **not** tune fusion weights to green these; they require company-scope
guards / abstention.

Next P0/P1 order:

1. Keep expanding labelled cases (target 40–50) and draft OCR/table/announcement slots.
2. Lower hard-negative@5 via section ownership + query-aware rerank (not global fusion weights).
3. Then P1 `duplicate_block_ratio` cleanup.

### 2026-08-03 - Expansion + query-aware rerank + duplicate cleanup

| Workstream | Result |
|---|---|
| Corpus | **54** cases (18 gate + 36 benchmark); announcement/research synthetic slots ready |
| Gate | **18/18** |
| hard-neg@5 | **0.67** (was 0.82) via section/metric penalties before rerank |
| Recall@5 / MRR@10 / nDCG@10 | 0.88 / 0.92 / 0.90 (explicit subset) |
| `duplicate_block_ratio` (znz) | **0.056** (was ~0.10); short-structure keep-first for banners |
| Non-regression | `core_metric_exact_match=1.0`, `source_grounding_rate=1.0` |

Code levers:

- `LocalRetriever._query_aware_adjustment` + `metric_keys` from orchestrator
- `DocumentCleaningService` repeated banner / short-structure keep-first
- Synthetic fixtures: `data/fixtures/joint_retrieval/huaheng_*.json`

Still open:

- Gongtong OCR+table subset Serving-ingested (`data/fixtures/joint_retrieval/gongtong_2021_ocr_table_subset.pdf`); joint sample `gongtong_2021` ready
- Cross-company abstain (3 red) needs company-scope guard
- `duplicate_block_ratio` target ≤0.03 not yet met (now 0.056)

### 2026-08-03 - Joint corpus freeze (baseline)

Frozen after corpus expansion + company-scope abstain + gongtong OCR ingest.

| Item | Value |
|---|---|
| Documents | **10** (ready + synthetic_ready) |
| Questions | **95** (gate 18 + benchmark 77) |
| Gate / joint | **18/18** / **95/95** |
| Recall@5 / MRR@10 / nDCG@10 | ≈0.91 / 0.90 / 0.90 |
| hard-neg@5 | ≈0.50 (soft debt; not blocking) |
| abstention | **1.0** (24 cases) |

Artifacts:

- `data/reports/joint_retrieval_benchmark/baseline_joint_retrieval_benchmark.json`
- `python scripts/run_joint_retrieval_benchmark.py --no-ablation --save-baseline`
- `python scripts/run_joint_retrieval_benchmark.py --no-ablation --compare-baseline`

**Policy for current documents:** stop expanding questions; do not tune fusion weights.
Resume ranking work only to chase soft-target green or production mis-ranking, via
query-aware / section ownership — not global fusion.
