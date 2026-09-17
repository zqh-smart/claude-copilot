# Financial workbench

Vue 3 + Vite + TypeScript + Element Plus application for Claude Copilot's financial-document workflows. It selectively references Yudao Lite frontend conventions without importing Yudao as a system dependency, adding its Java backend, or replacing the existing FastAPI contracts.

Implemented routes include dashboard, knowledge and graph inspection, research, comparison, reports, metrics, evaluation, jobs, uploads, and chat-memory inspection.

The workbench calls FastAPI through `/api/fastapi` and does not connect to
LangGraph directly. Full conversational Agent UX still lives in the independent
React app at `../chat-ui`; `/agent-chat` embeds that app in the Vue shell while
the assistant-ui runtime continues to own threads, streaming, and cancellation.

Use workspace commands from `frontend/`:

```bash
pnpm dev:workbench
pnpm --filter @claude-copilot/workbench build
```
