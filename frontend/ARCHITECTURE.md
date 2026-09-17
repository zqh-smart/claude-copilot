# Frontend architecture

Claude Copilot has two cooperating frontend applications, not one framework replacing the other.

> 金融工作台采用 Vue 3 + Vite + Element Plus；Agent Chat 改为 React + Vite + assistant-ui（接 LangGraph `:2025` 的 `agent` 图）。两者共享产品设计规范和业务协议，但保持框架、构建与运行时隔离。FastAPI 始终作为统一业务后端。

Yudao is an engineering reference and infrastructure source in this project, not a system-framework dependency.

```text
Browser
  ├─ /          Vue 3 + Vite workbench
  ├─ /chat/**   React + Vite + assistant-ui
  └─ /api/**    FastAPI business and agent gateway
```

## Application ownership

`apps/workbench` owns document ingestion, knowledge and graph inspection, hybrid-retrieval evaluation, metrics, research workflows, report authoring, jobs, and chat-memory inspection. It uses Element Plus with a Yudao-style administrative shell.

`apps/chat-ui` owns the full conversational Agent UX: thread list, message streaming, tool calls, interrupts, artifacts, and LangGraph SDK integration. The React component tree is not embedded in or copied into Vue. The chat surface is intentionally kept narrow — Tool UI / Generative UI / Citation panel are layered on top of the same assistant-ui primitives in later rounds without changing the workbench.

## Shared boundary

`packages/contracts` contains only Claude Copilot business DTOs such as document, metric, research, and Agent launch context. LangGraph `Message`, `Thread`, and transport types remain private to `apps/chat-ui`.

Each application reads its own environment variables. Contracts may describe public runtime configuration, but shared code must not combine `process.env` and `import.meta.env` access.

## Interaction and streaming

The workbench opens Agent Chat as a separate route. Business identifiers may be handed off as non-sensitive URL fields during the migration; the target design is an opaque context ID issued by FastAPI. Document text, credentials, and private metadata must never be placed in the URL. See `apps/chat-ui/src/lib/launch-context.ts` for the current handoff contract (`cc_source`, `cc_resource`, `cc_prompt`).

Workbench-only long tasks use REST plus SSE/fetch streaming for progress and draft deltas. This does not duplicate thread management or the full chat surface. assistant-ui's LangChain/LangGraph runtime is the recommended path for Agent Chat streaming, tool UI, and interrupts; it is not embedded in the workbench.

## Runtime topology

Development uses fixed ports:

- Workbench: `http://127.0.0.1:3000/`
- Chat: `http://127.0.0.1:3001/chat/`
- FastAPI: `http://127.0.0.1:8000/`
- LangGraph dev server: `http://127.0.0.1:2025/`

Production should expose one origin and route `/` to the workbench, `/chat/**` to the React+assistant-ui build, and `/api/**` to FastAPI. Authentication and Agent gateway credentials belong on the backend; no public frontend environment variable may contain a server API key.

## Why assistant-ui

`assistant-ui` is the official React primitive for Agent UX and ships first-class LangChain / LangGraph runtime support. Keeping chat-ui as React (instead of Next.js + `agent-chat-ui`) lets the frontend monorepo converge on a single dev model (Vite + React + Vite + Vue), preserves our `@claude-copilot/contracts` boundary, and gives future Tool UI / Generative UI / HITL work a single canonical primitive instead of three re-implementations across the workbench, the chat app, and the report editor. See `apps/chat-ui/RUNTIME.md` for the adapter contract.