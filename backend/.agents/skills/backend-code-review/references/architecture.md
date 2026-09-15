# Architecture review rules

## Intended layers

| Layer | Path | May depend on |
|-------|------|----------------|
| API routes | `app/api/v1/` | services, schemas, dependencies |
| API services | `app/api/services/` | core, pipeline, workflows |
| Pipeline | `app/pipeline/` | `src/claude_copilot` schemas, core storage/rag/kg as needed |
| Core | `app/core/` | schemas, external clients behind adapters |
| Domain | `src/claude_copilot/` | stdlib + pydantic only (prefer no FastAPI) |
| Workflows | `app/workflows/` | core retrieval/llm; keep graph nodes injectable |

## Red flags

- Business rules embedded in FastAPI route functions
- Concrete Qdrant/Neo4j/SQLAlchemy session usage outside `app/core/db` / `app/core/rag` / `app/core/kg` adapters
- New parallel schema types that duplicate `FinancialSchema` / `ParsedDocument`
- Workflow graphs importing API routers
- Skipping protocol boundaries when adding a backend

## Preferred patterns

- Construct graphs with injected callables (see `build_research_graph`)
- Configure via `app/core/config.py` Settings
- Persist documents/segments through repository protocols
