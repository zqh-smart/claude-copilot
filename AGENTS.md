# Claude Copilot

Monorepo for financial document intelligence.

```text
backend/   FastAPI + LangGraph. Python cwd is always backend/.
frontend/  Vue 3 workbench + React/Vite Agent Chat. Do not add pages to backend/web/.
```

- Disk root: `D:\GithubProject\claude-copilot`
- Workspace: `D:\GithubProject\claude-copilot.code-workspace`
- Python package name `claude_copilot` is historical; do not rename it when moving folders.
- Nested leftover `frontend/agent-chat-ui-main/` is not the product surface.
- Current execution order: [`NEXT.md`](NEXT.md). Architecture is frozen until the P0 suite in `frontend/apps/chat-ui/RUNTIME.md` is green.

Backend details: [`backend/AGENTS.md`](backend/AGENTS.md)
Frontend details: [`frontend/README.md`](frontend/README.md)
