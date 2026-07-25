---
name: backend-code-review
description: Review Claude Copilot backend Python for correctness, layering, protocols, financial provenance, and test coverage. Use when reviewing changes under app/ or src/claude_copilot/, PRs, or when the user asks for a backend code review. Do not use for unrelated frontend/UI repos.
---

# Backend Code Review

## When to use

Review Python under:

- `app/api/`, `app/core/`, `app/pipeline/`, `app/workflows/`
- `src/claude_copilot/`
- related `tests/` and `scripts/`

Modes: pending-change review, pasted snippets, or named files.

## Process

1. Identify scope (diff / files / snippet) and keep review tight.
2. Apply the checklist below; use [references/architecture.md](references/architecture.md) for layering and [references/financial-invariants.md](references/financial-invariants.md) for domain rules.
3. Output findings with severity and actionable fixes (`path:line` when possible).

## Checklist

### Architecture & layering

- [ ] Routes stay thin; logic in services / pipeline / core
- [ ] Domain models in `src/claude_copilot/schemas/`, not duplicated ad-hoc dicts in API
- [ ] Dependencies flow inward via protocols (`*Protocol`) and `dependencies.py`
- [ ] No circular imports between pipeline and API

### Financial document correctness

- [ ] Status transitions go through `ensure_transition`
- [ ] Schema/mapping changes preserve provenance on facts
- [ ] PDF route names and metadata fields remain stable
- [ ] Embedding/collection changes call out reindex/backfill needs

### Data & backends

- [ ] Postgres/Qdrant/Neo4j usage stays behind repository / store adapters
- [ ] Local JSON fallbacks still work for tests when touching storage
- [ ] No hardcoded secrets; use settings / env

### Quality

- [ ] Type hints present; avoid unnecessary `Any`
- [ ] Domain errors from `app/core/errors.py` where appropriate
- [ ] Focused tests for behavior changes (`uv run pytest` path noted)
- [ ] Change scope matches karpathy guidelines (no drive-by refactors)

## Required output format

```markdown
## Summary
One paragraph.

## Findings
### Critical
- ...

### Suggestions
- ...

### Nice to have
- ...

## Testing gaps
- ...
```

## General security / performance

Flag SQL injection, SSRF, command injection, secret leakage, N+1 queries, and blocking I/O on request paths when present in scope.
