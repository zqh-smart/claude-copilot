# AGENTS.md

## Project Overview

Claude Copilot is a financial document intelligence system. Phase 1 focuses on the document processing foundation (upload → parse → structure → schema → chunk → index → graph), then hybrid retrieval and grounded research via LangGraph.

Engineering references (multi-root workspace):

- **Dify**: document pipeline patterns (parser router, status machine, segments, indexing)
- **agent-chat-ui-main**: **sole frontend home** — Agent Chat + knowledge/workbench pages
- **LangGraph**: multi-step research orchestration with critic/revision loops

## Layout

```text
claude_copilot/                  # Backend only for UI purposes (this repo)
├── app/                         # Runtime
│   ├── api/                     # FastAPI routes + thin services
│   ├── core/                    # config, db, rag, kg, llm, prompts, errors
│   ├── pipeline/feature_pipeline/  # Document AI pipeline (primary focus)
│   └── workflows/               # Live LangGraph graphs: research/risk/quant/compare/report/orchestrator
├── web/                         # DEPRECATED Vite console (frozen; do not add features)
├── src/claude_copilot/          # Installable domain package (schemas, entity resolution)
├── tests/                       # pytest
├── scripts/                     # backfill, smoke, benchmarks
├── data/                        # documents, golden, fixtures, reports
├── docs/                        # architecture and API docs
└── .agents/skills/              # Agent skills for this repo

# Sibling workspace folder (not in this repo):
agent-chat-ui-main/              # Next.js — ALL frontend pages (chat + workbench)
```

**Boundary rules:**

- Domain contracts live in `src/claude_copilot/schemas/`.
- Runtime orchestration lives in `app/`.
- Prefer protocols (`*Protocol`) over concrete backends so local JSON / Postgres / Qdrant / Neo4j stay swappable.
- Keep API routes thin; business logic in services / pipeline / core.
- **All frontend pages** (Agent Chat, 知识库, 研究问答, 对比, 报告, BI, 评测, 任务, 上传) live in sibling `agent-chat-ui-main`. Do **not** add UI in `claude_copilot/web/`.
- `claude_copilot/web/` is deprecated leftover; keep compiling only; no new features.

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

# Product frontend (separate terminal) — agent-chat-ui-main
# pnpm dev → http://localhost:3000  (Chat + /knowledge /research /eval …)
# Workbench calls FastAPI :8000 via /api/fastapi proxy; Chat uses LangGraph :2025
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

Product UI: see `docs/acceptance_suite.md` §0 (`agent-chat-ui-main` :3000).

## Agent Chat UI (sibling) — sole frontend

All user-facing pages live in workspace folder `agent-chat-ui-main` (Next.js):

- `/` — Agent Chat → LangGraph `:2025` graph `agent`
- `/knowledge` `/chat-memory` `/research` `/compare` `/reports` `/metrics` `/eval` `/jobs` `/upload` — workbench → FastAPI `:8000` (via `/api/fastapi` proxy)

**Chat 记忆**（可选）：MemoryCore sidecar `:8420`，与文档三库分离。见 `docs/chat_memory.md`。

### 1) Start stack (Windows)

```powershell
docker compose up -d postgres qdrant neo4j redis

# optional Chat memory sidecar (needed when CHAT_MEMORY_ENABLED=true)
.\scripts\run_memory_core.ps1

# FastAPI
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# LangGraph agent (isolated .venv-langgraph)
$env:PYTHONUTF8='1'
.\scripts\run_agent_langgraph.ps1
# → http://127.0.0.1:2025   graph id: agent  (override with LANGGRAPH_PORT)

# optional: pin a Serving doc in langgraph.env
# AGENT_CHAT_DOC_ID=<doc_uuid>
# CHAT_MEMORY_ENABLED=true
```

### 2) Start Agent Chat UI

```bash
cd ../agent-chat-ui-main
# .env already points to localhost:2025 / assistant=agent
pnpm install
pnpm dev   # http://localhost:3000
```

Do not add frontend pages in `claude_copilot/web/` (deprecated).  
L3 评测看板 / 知识库 / 切片 / 图谱 / 对话记忆：`/eval`、`/knowledge`、`/chat-memory`。

## Coding Conventions

- Python ≥3.11, Pydantic v2 models, explicit type hints (avoid `Any` unless metadata bags)
- Domain exceptions in `app/core/errors.py`
- Match nearby patterns; keep changes small (see `.agents/skills/karpathy-guidelines`)
- Financial cues may be bilingual (EN/ZH) in parsers and prompts
- Prefer editing existing modules over adding parallel abstractions

## Docs Index

- `docs/agent_chat_ui.md` — Agent Chat UI ↔ LangGraph `agent` bridge
- `docs/chat_memory.md` — MemoryCore sidecar Chat memory（≠ 三库文档知识）
- `docs/tencent_memory_and_ui_adoption_plan.md` — Chat memory + UI 采用改造清单
- `docs/project_architecture.md` — module boundaries
- `docs/knowledge_graph.md` — graph model and backfill
- `docs/structured_financial_data_api.md` — companies/metrics/research API
- `docs/evaluation_system.md` — layered eval (L0–L4) +入库闸门（先评后存）
- `docs/acceptance_suite.md` — smoke/regression commands and pass criteria
- `docs/eval_metrics.md` — stage metrics definitions (L1/L2 detail)
- `docs/pipeline_eval_status.md` — current scorecard snapshot + next optimizations
- `docs/loop_playbook.md` — autonomous `/loop` instructions（Phase G 已完成；Phase H 深化主线）
- `docs/phase_h_acceptance.md` — Phase H 六项任务的样本、指标公式、硬阈值、命令与报告契约
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
