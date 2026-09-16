# Agent Chat (assistant-ui)

React + Vite + [assistant-ui](https://www.assistant-ui.com) implementation of Claude Copilot's Agent Chat surface. It is a sibling to the Vue workbench; the two share business DTOs via `@claude-copilot/contracts` but never import each other's components.

## Dev

```bash
# from frontend/
pnpm install                  # first install (bootstrap); resolves the caret ranges
# ↑ IMPORTANT: the @assistant-ui/* baseline is a compatibility SET, not a shared
# minor version (react 0.15.x / react-langgraph 0.14.x / react-markdown 0.14.x).
# Versions are already pinned exactly in package.json — do NOT re-introduce `^`.
# After any dependency change, commit package.json + pnpm-lock.yaml together and
# use `pnpm install:frozen` (== pnpm install --frozen-lockfile) in CI.
# See apps/chat-ui/RUNTIME.md §Lockfile policy.
pnpm dev:chat                  # http://127.0.0.1:3001/chat/
```

Required backend services:

- LangGraph dev server on `:2025` — `backend/scripts/run_agent_langgraph.ps1`
- FastAPI on `:8000` — only needed if you want the Workbench handoff banner to deep-link to a real resource.

## Launch context from the Workbench

The Workbench opens `http://127.0.0.1:3001/chat/?cc_source=<src>&cc_resource=<id>&cc_prompt=<text>`. See `src/lib/launch-context.ts` for parsing and `apps/chat-ui/RUNTIME.md` for the full contract.

## Stack

- Vite 6, React 19, TypeScript 5.8
- `@assistant-ui/react` for Thread / Composer / ThreadList primitives
- `@assistant-ui/react-markdown` for message rendering
- `tailwindcss` 3 + `@radix-ui/react-*` primitives
- `react-router-dom` for the in-app `/` route (chat lives at `/chat/` in production)

## Where to extend

- Tool UI / Generative UI / citation panel → `src/routes/ChatThread.tsx`
- Custom thread list / filters / search → `src/components/ThreadList.tsx`
- Alternate LLM / cloud runtime swap → `src/runtime/langgraph.ts`