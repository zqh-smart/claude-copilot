# Claude Copilot frontend

The frontend workspace contains two applications with explicit ownership:

- `apps/workbench`: Vue 3 + Vite + Element Plus financial workbench that selectively references Yudao Lite administration patterns.
- `apps/chat-ui`: Next.js agent-chat-ui for complete Agent/LangGraph chat behavior.
- `packages/contracts`: framework-neutral Claude Copilot business DTOs.

This is protocol-level integration, not component-level compatibility. React components from agent-chat-ui are not mounted inside Vue, and LangGraph SDK `Message` or `Thread` types are not shared with the workbench.

## Requirements

- Node.js 24.21.0
- pnpm 10.18.3
- FastAPI backend on port 8000

## Install and run

From this directory:

```bash
pnpm install
pnpm dev
```

Or run each application separately:

```bash
pnpm dev:workbench
pnpm dev:chat
```

Development URLs:

- Workbench: `http://127.0.0.1:3000`
- Agent Chat: `http://127.0.0.1:3001/chat`

Build and type-check:

```bash
pnpm typecheck
pnpm build
```

Copy the application-specific `.env.example` files when local overrides are needed. Never expose a LangSmith or backend API key through a `VITE_*` or `NEXT_PUBLIC_*` variable.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for product boundaries, streaming policy, and production routing.
