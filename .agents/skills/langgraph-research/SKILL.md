---
name: langgraph-research
description: Guides the LangGraph financial research workflow — ResearchState, retrieve→synthesize→critique→revise loop, grounded synthesis, and research API integration. Use when editing app/workflows/research, ResearchService, grounded_research, financial analysis prompts, or critic/revision behavior.
---

# LangGraph Research

## Scope

- Graph: `app/workflows/research/graph.py`
- Service: `app/api/services/research_service.py`
- API: `app/api/v1/research.py` → `POST /api/v1/research/query`
- Grounding: `app/core/llm/grounded_research.py`
- Prompts: `app/core/prompts/financial_analysis.py`
- State schemas: `src/claude_copilot/schemas/research.py`
- Tests: `tests/core/llm/`, research paths in `tests/test_documents.py`

## Graph shape

```text
START → retrieve_context → synthesize_answer → critique_answer
                              ↑                    │
                              └── revise_answer ←──┘ (if critic fails & revisions left)
                                                   ↓
                                                  END
```

`ResearchState` carries: question, hits, metrics, graph_paths, evidence, synthesis, critic, revision_count, answer.

If LangGraph import fails, `build_research_graph` returns `_FallbackCompiledGraph` with the same control flow — preserve that fallback when changing node contracts.

## Working rules

1. **Ground answers in evidence** — prefer orchestrator hits, SQL metrics, and graph paths over free-form hallucination.
2. Keep node functions pure-ish: accept state dict-like input, return partial state updates.
3. Critic should check citation/grounding quality; revision must consume critic feedback.
4. Do not remove the fallback graph path without an explicit decision.
5. `risk/`, `reporting/`, `comparison_workflow/`, and `report_workflow/` are live graphs;
   preserve their tested state contracts when wiring research or orchestration.

## Change checklist

- [ ] Update `ResearchState` keys consistently across nodes + service
- [ ] Keep retrieve node aligned with `RetrievalOrchestrator` output shape
- [ ] Prompts stay in `app/core/prompts/` (versionable), not inlined in routes
- [ ] Add/adjust tests for critic pass/fail and max_revisions behavior
- [ ] Verify API preview still works with LLM disabled / hash fallbacks when applicable

## Anti-patterns

- Putting retrieval or DB logic directly in FastAPI route handlers
- Ignoring `warnings` from hybrid retrieval in the final answer
- Duplicating the existing risk/reporting/comparison graphs instead of extending their contracts
