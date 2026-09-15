# Claude Copilot

金融文档智能：文档解析入库 → Postgres / Qdrant / Neo4j 三库检索与图谱 → LangGraph 研究编排 → Agent Chat 工作台。

本仓库是前后端合一的 monorepo。

```text
claude-copilot/
├── backend/    FastAPI + LangGraph（文档管线、检索、研究图、Chat Memory）
└── frontend/   Next.js 产品 UI（Agent Chat + 知识库 / 报告 / 评测等工作台）
```

打开 Cursor 工作区：`D:\GithubProject\claude-copilot.code-workspace`，或本目录下的 `claude-copilot.code-workspace`。

## 启动

```powershell
# 0) 三库
cd D:\GithubProject\claude-copilot\backend
docker compose up -d postgres qdrant neo4j redis

# 1) FastAPI :8000
uv run uvicorn app.main:app --reload --port 8000

# 2) LangGraph agent :2025
$env:PYTHONUTF8='1'
.\scripts\run_agent_langgraph.ps1

# 3) UI :3000
cd D:\GithubProject\claude-copilot\frontend
pnpm install
pnpm dev
```

浏览器：http://localhost:3000
- `/chat` Agent Chat
- `/knowledge` `/reports` `/research` 等工作台走 `/api/fastapi` → FastAPI `:8000`

更细的后端约定见 [`backend/AGENTS.md`](backend/AGENTS.md) 与 [`backend/README.md`](backend/README.md)。前端见 [`frontend/README.md`](frontend/README.md)。

`backend/web/` 已废弃，不要在那里加页面。
