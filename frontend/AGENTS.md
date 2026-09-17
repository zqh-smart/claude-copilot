# Claude Copilot frontend

> **Architecture Frozen. No further framework/runtime changes before P0 acceptance.**

The frontend workspace contains two cooperating applications with explicit ownership:

- `apps/workbench`: Vue 3 + Vite + Element Plus financial workbench.
- `apps/chat-ui`: React + Vite + assistant-ui Agent Chat surface.
- `packages/contracts`: framework-neutral Claude Copilot business DTOs.

- Treat `apps/workbench` and `apps/chat-ui` as separate product applications.
- Keep financial workflows in the Vue 3/Vite workbench and complete conversational agent UX in the React + assistant-ui chat app.
- Never import React UI from chat-ui into the workbench, or Vue UI from the workbench into chat-ui.
- Framework-neutral Claude Copilot DTOs live in `packages/contracts`. Each app owns its environment-variable adapter (`import.meta.env` in chat-ui, `VITE_*` in workbench).
- Workbench streaming is limited to task/report progress over backend REST/SSE. Do not recreate full Agent Chat there.
- Keep development URLs stable: workbench `http://127.0.0.1:3000/`, chat `http://127.0.0.1:3001/chat/`, FastAPI `http://127.0.0.1:8000/`, LangGraph dev server `http://127.0.0.1:2025/`. Production routes `/`, `/chat/**`, `/api/**` on one origin.
- Only public configuration belongs in `VITE_*` env vars. Long-lived secrets (LangSmith / LangGraph API keys, LLM tokens) MUST travel server-to-server via FastAPI BFF — never through `import.meta.env`.
- assistant-ui + `@assistant-ui/react-langgraph` is the canonical primitive for chat-ui Agent UX. Avoid re-implementing thread / tool / interrupt widgets from scratch.
- Run `apps/chat-ui/RUNTIME.md`'s 15-item acceptance suite (build / TS / thread list / switch / refresh / cancel / thread isolation / hard-refresh launch context / end-to-end cancellation) before starting any Tool UI / Generative UI work.
- The chat-ui stack (React 19 + Vite + assistant-ui + `@assistant-ui/react-langgraph` + `@langchain/langgraph-sdk` + LangGraph `:2025`) is **frozen** at P0 acceptance. Do not introduce `react-langchain` or any other runtime without an explicit ADR.
- **Current gate**: `Architecture Frozen → P0 Runtime Acceptance`. Do not start Tool UI / Generative UI / HITL work until the 15-item suite in `apps/chat-ui/RUNTIME.md` is green.
- `@assistant-ui/*` is pinned as a **compatibility set, not a minor version** — the three packages do not share a minor line (`react` 0.15.x / `react-langgraph` 0.14.x / `react-markdown` 0.14.x). Exact versions are pinned in `apps/chat-ui/package.json`; do not re-introduce caret ranges or bump outside an explicit upgrade task. The `0.13.x` baseline in earlier revisions was a false baseline and never installable. See `apps/chat-ui/RUNTIME.md` §Versioning.
- `unstable_createLangGraphStream` and `unstable_threadListAdapter` are the two `unstable_*` helpers we rely on. Pin patch versions and run the 15-item acceptance suite on every assistant-ui bump.
- Treat Yudao UI Admin Vue3 as a source of selected frontend practices only. Never add its Java/RuoYi backend protocols, permission APIs, or code-generation backend.