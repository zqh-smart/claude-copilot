---
name: hybrid-retrieval
description: Guides hybrid RAG for financial documents — embeddings, Qdrant indexing, reranking, and RetrievalOrchestrator routing (semantic / structured / hybrid). Use when editing app/core/rag, chunking/indexing for vectors, backfill_qdrant, research retrieve_context, or retrieval smoke scripts.
---

# Hybrid Retrieval

## Scope

- RAG core: `app/core/rag/` (`embeddings`, `vector_store`, `retriever`, `reranking`, `orchestrator`, `query_expansion`)
- Chunk/index: `app/pipeline/feature_pipeline/chunking/`, `indexing/`
- Wiring: `app/api/dependencies.py`
- Smoke: `scripts/run_retrieval_smoke.py`, `scripts/backfill_qdrant.py`

## Evidence channels

`RetrievalOrchestrator` fuses:

| Channel | Source | Typical use |
|---------|--------|-------------|
| Vector / lexical | Qdrant + retriever | narrative, MD&A, risk text |
| Structured metrics | financial data repo / SQL | exact figures, trends |
| Graph paths | knowledge graph store | company–metric–risk relations |

Query analysis routes intent to `semantic` | `structured` | `hybrid`. Prefer improving routing cues over forcing one channel.

## Working rules

1. Respect embedding dimension / collection naming (default collection tied to BGE-M3 / configured model). Changing the embedding model requires reindex/backfill.
2. Use `VectorStoreProtocol` — do not hardcode Qdrant calls outside the vector store adapter.
3. Tests may use `HashEmbeddingService` / noop store; production path uses Silicon embeddings + Qdrant when configured.
4. Segment metadata must remain stable enough for filters (document_id, section types, pages).
5. After chunking or embedding changes, run backfill before trusting retrieval smoke results.

## Commands

```bash
uv run python scripts/backfill_qdrant.py
uv run python scripts/run_retrieval_smoke.py
uv run pytest tests/core/rag -q
```

## Anti-patterns

- Mixing hash and real embeddings against the same Qdrant collection
- Returning ungrounded numbers from LLM when structured metrics are available
- Ignoring orchestrator warnings / empty-hit handling in research retrieve node
