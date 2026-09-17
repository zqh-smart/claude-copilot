# Claude Copilot frontend

The frontend workspace contains two cooperating applications with explicit ownership:

- `apps/workbench`: Vue 3 + Vite + Element Plus financial workbench.
- `apps/chat-ui`: React + Vite + [assistant-ui](https://www.assistant-ui.com) Agent Chat surface, backed by the LangGraph `agent` graph.
- `packages/contracts`: framework-neutral Claude Copilot business DTOs.

This is protocol-level integration, not component-level compatibility. Vue and React components never cross applications, and LangGraph SDK `Message` / `Thread` types stay inside `apps/chat-ui`.

## Requirements

- Node.js 24.21.0
- pnpm 10.18.3
- FastAPI backend on port 8000
- LangGraph dev server on port 2025 (`backend/scripts/run_agent_langgraph.ps1`)

## Install and run

From this directory:

```bash
pnpm install
pnpm dev          # workbench + chat-ui in parallel
```

Or run each application separately:

```bash
pnpm dev:workbench
pnpm dev:chat
```

Development URLs:

- Workbench: `http://127.0.0.1:3000/`
- Agent Chat: `http://127.0.0.1:3001/chat/` (Workbench opens this in a new tab from the top-bar "Agent Chat" button)

Build and type-check:

```bash
pnpm typecheck
pnpm build
```

Copy the application-specific `.env.example` files when local overrides are needed. Never expose a LangSmith or backend API key through a `VITE_*` variable — those are bundled into the client.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for product boundaries, streaming policy, and production routing. See [apps/chat-ui/RUNTIME.md](./apps/chat-ui/RUNTIME.md) for the assistant-ui ↔ LangGraph wiring.