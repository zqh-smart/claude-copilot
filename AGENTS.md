# Claude Copilot

Monorepo for financial document intelligence.

```text
backend/   FastAPI + LangGraph. Python cwd is always backend/.
frontend/  Next.js product UI. Do not add pages to backend/web/.
```

- Disk root: `D:\GithubProject\claude-copilot`
- Workspace: `D:\GithubProject\claude-copilot.code-workspace`
- Python package name `claude_copilot` is historical; do not rename it when moving folders.
- Nested leftover `frontend/agent-chat-ui-main/` is not the product surface.

Backend details: [`backend/AGENTS.md`](backend/AGENTS.md)
Frontend details: [`frontend/README.md`](frontend/README.md)
