# AGENTS.md

## Project Overview

Claude Copilot is a financial document intelligence system. Phase 1 focuses on the document processing foundation (upload → parse → structure → schema → chunk → index → graph), then hybrid retrieval and grounded research via LangGraph.

Engineering references (multi-root workspace):

- **Dify**: document pipeline patterns (parser router, status machine, segments, indexing)
- **agent-chat-ui-main**: LangGraph agent chat pages (`messages` UI); owns all subsequent agent-facing UI
- **LangGraph**: multi-step research orchestration with critic/revision loops

## Layout

```text
claude_copilot/                  # Backend + internal console (this repo)
├── app/                         # Runtime
│   ├── api/                     # FastAPI routes + thin services
│   ├── core/                    # config, db, rag, kg, llm, prompts, errors
│   ├── pipeline/feature_pipeline/  # Document AI pipeline (primary focus)
│   └── workflows/               # LangGraph graphs (research live; risk/reporting stubs)
├── web/                         # Vite console: docs / research Q&A / metrics / L3 eval (not agent chat)
├── src/claude_copilot/          # Installable domain package (schemas, entity resolution)
├── tests/                       # pytest
├── scripts/                     # backfill, smoke, benchmarks
├── data/                        # documents, golden, fixtures, reports
├── docs/                        # architecture and API docs
└── .agents/skills/              # Agent skills for this repo

# Sibling workspace folder (not in this repo):
agent-chat-ui-main/              # Next.js Agent Chat UI → LangGraph `messages` chat pages
```

**Boundary rules:**

- Domain contracts live in `src/claude_copilot/schemas/`.
- Runtime orchestration lives in `app/`.
- Prefer protocols (`*Protocol`) over concrete backends so local JSON / Postgres / Qdrant / Neo4j stay swappable.
- Keep API routes thin; business logic in services / pipeline / core.
- **Agent chat UI**: implement/change in `agent-chat-ui-main`, not in `claude_copilot/web/`.
- **L3 / docs workbench**: stay in `claude_copilot/web/` (eval board + research cards).

## Default Commands

Use `uv` for all Python work:

```bash
uv sync
uv sync --extra pdf_ocr --extra pdf_mineru   # optional PDF backends
uv sync --extra dev                          # pytest, ruff, mypy

uv run pytest -q
uv run ruff check .
uv run uvicorn app.main:app --reload
docker compose up -d                         # postgres, qdrant, redis, neo4j

# Workspace console (separate terminal)
cd web && npm install && npm run dev         # http://localhost:5173 → proxies /api to :8000
```

## Document Pipeline

Ordered stages in `app/pipeline/feature_pipeline/`:

1. **Parse** (`parser/`) — extension router; PDF routes: `native_pdf` / `ocr_pdf` / `table_pdf` / `mineru_pdf`
2. **Clean** (`cleaning/`) — remove headers/footers, TOC noise, duplicate marginal lines
3. **Segment** (`segmentation/`) — MD&A, risk, notes, etc. (strict title anchors + merge)
4. **Table intelligence** (`table_intelligence/`) — classify statements / notes, normalize periods/metrics
5. **Structure** (`structure_reconstruction/`) — rebuild sections from blocks/tables
6. **Schema mapping** (`schema_mapping/`) — build `FinancialSchema`
7. **Chunk** (`chunking/`) — section-aware segments for indexing
8. **Index** (`indexing/`) — segment repo + vector store
9. **Knowledge graph** (`app/core/kg/`) — Company / Document / Metric / Risk nodes

Status machine (`state_machine.py`):

`waiting → parsing → cleaning → chunking → indexing → completed` (plus `paused` / `failed`).

Do not skip schema mapping before chunking when financial structure is required.

## Backends

Configured via `.env` / `app/core/config.py`:

| Concern | Env / setting | Options |
|---------|---------------|---------|
| Document storage | `STORAGE_BACKEND` | local JSON or Postgres |
| Vectors | `VECTOR_STORE_BACKEND` | noop / Qdrant |
| Graph | `GRAPH_STORE_BACKEND` | local JSON / Neo4j |
| PDF priority | `PDF_PARSER_BACKEND_PRIORITY` | default `mineru_pdf,table_pdf,native_pdf,ocr_pdf` |

Composition root: `app/api/dependencies.py`.

## Research Workflow

LangGraph graph in `app/workflows/research/graph.py`:

`retrieve_context → synthesize_answer → critique_answer ⇄ revise_answer → END`

API: `POST /api/v1/research/query`. Hybrid evidence comes from `RetrievalOrchestrator` (vector + SQL metrics + graph paths).

## Testing

- Framework: pytest (`uv run pytest -q`)
- Layout mirrors `app/` and `tests/core/...`
- Prefer Arrange-Act-Assert; wire services with `tmp_path` and FastAPI dependency overrides
- Golden expectations: `data/golden/`
- Parser/PDF suites: `tests/test_parsers.py`
- Smoke/backfill scripts under `scripts/` write artifacts to `data/reports/`

## Stage Evaluation (before/after optimization)

Use stage scorecards so changes are judged positive/negative, not by vibes:

- Metrics spec: `docs/eval_metrics.md`
- Runner: `uv run python scripts/run_stage_eval.py --save-baseline`
- Compare: `uv run python scripts/run_stage_eval.py --compare-baseline`
- Outputs: `data/reports/eval/latest_scorecard.json`, `baseline_scorecard.json`, `diff_vs_baseline.json`

Key signals: `core_metric_exact_match` and `source_grounding_rate` must not regress; watch `false_anchor_rate_proxy`, `implausible_period_ratio`, `tiny_segment_ratio`.

Serving ingest + L3 retrieval eval:

```bash
docker compose up -d postgres qdrant neo4j
python scripts/run_serving_ingest_eval.py
```

Acceptance suite (smoke / regression profiles): `docs/acceptance_suite.md`

```bash
python scripts/run_acceptance_suite.py --profile smoke
python scripts/run_acceptance_suite.py --profile regression
python scripts/run_acceptance_suite.py --profile all          # smoke then regression gate
```

Workspace UI: see `docs/acceptance_suite.md` §0 (`web/` Vite console).

## Agent Chat UI (sibling)

Agent-facing chat pages live in workspace folder `agent-chat-ui-main` (Next.js, LangGraph `messages`).

```bash
cd ../agent-chat-ui-main
pnpm install
pnpm dev   # http://localhost:3000
```

Do not grow a parallel agent chat product inside `claude_copilot/web/`.  
L3 pass_rate / 逐题对错看板仍在本仓库 `web/`「评测看板」页（`GET /api/v1/eval/serving*`）。

## Coding Conventions

- Python ≥3.11, Pydantic v2 models, explicit type hints (avoid `Any` unless metadata bags)
- Domain exceptions in `app/core/errors.py`
- Match nearby patterns; keep changes small (see `.agents/skills/karpathy-guidelines`)
- Financial cues may be bilingual (EN/ZH) in parsers and prompts
- Prefer editing existing modules over adding parallel abstractions

## Docs Index

- `docs/project_architecture.md` — module boundaries
- `docs/knowledge_graph.md` — graph model and backfill
- `docs/structured_financial_data_api.md` — companies/metrics/research API
- `docs/evaluation_system.md` — layered eval (L0–L4) +入库闸门（先评后存）
- `docs/acceptance_suite.md` — smoke/regression commands and pass criteria
- `docs/eval_metrics.md` — stage metrics definitions (L1/L2 detail)
- `docs/pipeline_eval_status.md` — current scorecard snapshot + next optimizations
- `README.md` — onboarding, env, scripts

## Skills Index

Project skills live under `.agents/skills/`:

| Skill | Use when |
|-------|----------|
| `karpathy-guidelines` | Any coding change |
| `document-pipeline` | Pipeline stages, status machine, post-parse flow |
| `pdf-routing` | PDF backends, route selection, optional extras |
| `financial-schema-mapping` | Tables → `FinancialSchema`, metrics, golden data |
| `hybrid-retrieval` | RAG, Qdrant, orchestrator query routing |
| `knowledge-graph` | KG builder, entity resolution, Neo4j/local |
| `langgraph-research` | Research graph, critic loop, grounded answers |
| `backend-code-review` | Reviewing Python under `app/` / `src/` |
