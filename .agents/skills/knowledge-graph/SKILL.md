---
name: knowledge-graph
description: Guides financial knowledge graph build and storage — nodes/edges from FinancialSchema, entity resolution, local JSON vs Neo4j, and GraphRAG paths used in retrieval. Use when editing app/core/kg, knowledge_graph schemas, entity_resolution, backfill_knowledge_graph, or graph-backed research evidence.
---

# Knowledge Graph

## Scope

- Builder / extractor / stores: `app/core/kg/`
- Schemas: `src/claude_copilot/schemas/knowledge_graph.py`
- Entity IDs: `src/claude_copilot/entity_resolution.py`
- Docs: `docs/knowledge_graph.md`
- Backfill: `scripts/backfill_knowledge_graph.py`
- Tests: `tests/core/kg/`

## Model intent

Build graph evidence from `ParsedDocument` + `FinancialSchema`:

- **Nodes**: Company, Document, Metric, Risk, and related types as implemented
- **Edges**: document ownership, metric observations, risk mentions, subsidiary/industry links where extracted
- **Paths**: returned to `RetrievalOrchestrator` / research as `graph_paths`

Prefer deterministic `entity_resolution` for company IDs (normalize Unicode, strip legal suffixes) over ad-hoc string equality.

## Backends

| Backend | When |
|---------|------|
| Local JSON | Default/dev, offline tests |
| Neo4j | `GRAPH_STORE_BACKEND` / docker compose Neo4j |

Use `KnowledgeGraphStoreProtocol` — keep builder store-agnostic.

## Working rules

1. Build from schema facts with provenance when possible — avoid inventing metrics not in `FinancialSchema`.
2. Keep node/relationship type names stable (API + retrieval depend on them).
3. Re-run backfill after schema mapping or entity resolution changes.
4. Graph is an evidence channel, not a replacement for vector retrieval or SQL metrics.

## Commands

```bash
uv run python scripts/backfill_knowledge_graph.py
uv run pytest tests/core/kg -q
```

## Checklist for changes

- [ ] Schema → node/edge mapping updated in builder/extractor
- [ ] Entity resolution covered for new alias patterns
- [ ] Store protocol + both backends considered (or explicitly local-only)
- [ ] Retrieval/orchestrator still consumes path shape correctly
