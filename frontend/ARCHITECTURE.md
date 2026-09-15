# Frontend architecture

Claude Copilot has two cooperating frontend applications, not one framework replacing the other.

> 金融工作台采用 Vue 3 + Vite + Element Plus，并渐进式吸收 Yudao UI Admin Vue3 的后台工程能力；完整 Agent Chat 独立采用 Next.js agent-chat-ui。两者共享产品设计规范和业务协议，但保持框架、构建与运行时隔离。FastAPI 始终作为统一业务后端，不引入 Yudao Java 后端体系。

Yudao is an engineering reference and infrastructure source in this project, not a system-framework dependency.

```text
Browser
  ├─ /          Vue 3 + Vite workbench
  ├─ /chat/**   Next.js agent-chat-ui
  └─ /api/**    FastAPI business and agent gateway
```

## Application ownership

`apps/workbench` owns document ingestion, knowledge and graph inspection, hybrid-retrieval evaluation, metrics, research workflows, report authoring, jobs, and chat-memory inspection. It uses Element Plus with a Yudao-style administrative shell.

`apps/chat-ui` owns full conversational Agent UX: threads, message streaming, tool calls, interrupts, artifacts, and LangGraph SDK integration. The React component tree is not embedded in or copied into Vue.

## Shared boundary

`packages/contracts` contains only Claude Copilot business DTOs such as document, metric, research, and Agent launch context. LangGraph `Message`, `Thread`, and transport types remain private to `apps/chat-ui`.

Each application reads its own environment variables. Contracts may describe public runtime configuration, but shared code must not combine `process.env` and `import.meta.env` access.

## Interaction and streaming

The workbench opens Agent Chat as a separate route. Business identifiers may be handed off as non-sensitive URL fields during the migration; the target design is an opaque context ID issued by FastAPI. Document text, credentials, and private metadata must never be placed in the URL.

Workbench-only long tasks use REST plus SSE/fetch streaming for progress and draft deltas. This does not duplicate thread management or the full chat surface. AG-UI may later be introduced behind an adapter, but is not a replacement assumption for agent-chat-ui.

## Runtime topology

Development uses fixed ports:

- Workbench: `http://127.0.0.1:3000`
- Chat: `http://127.0.0.1:3001/chat`
- FastAPI: `http://127.0.0.1:8000`

Production should expose one origin and route `/` to the workbench, `/chat/**` to Next.js, and `/api/**` to FastAPI. Authentication and Agent gateway credentials belong on the backend; no public frontend environment variable may contain a server API key.
