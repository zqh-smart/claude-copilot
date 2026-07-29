# Agent Chat UI 对接说明

`agent-chat-ui-main` 需要 **LangGraph Server**（默认 `http://localhost:2024`），图 ID 为 `agent`（`messages` state）。

## 架构

```text
browser :3000 (agent-chat-ui)
    → LangGraph API :2024  graph=agent
        → app/workflows/agent_chat/graph.py
            → ResearchService.preview(doc_id, question)
                → Postgres / Qdrant / LLM
```

内部工作台 `web/:5173` 仍直连 FastAPI `:8000`（文档 / L3），不经过本桥。

## 启动

```powershell
# Terminal A — FastAPI（可选，工作台用）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Terminal B — LangGraph agent（Agent Chat 必需；Windows 推荐）
$env:PYTHONUTF8='1'
.\scripts\run_agent_langgraph.ps1
# → http://127.0.0.1:2024  graph id=agent

# Terminal C — UI
cd ..\agent-chat-ui-main
pnpm install
pnpm dev
```

打开 http://localhost:3000 ，Deployment URL=`http://localhost:2024`，Assistant=`agent`。

## doc_id

优先顺序：

1. LangGraph `configurable.doc_id`
2. 环境变量 `AGENT_CHAT_DOC_ID`
3. 最新 `data/reports/serving_eval/*_serving_eval.json` 的 `doc_id`

## 文件

| 路径 | 作用 |
|------|------|
| `langgraph.json` | 注册 graph `agent` |
| `app/workflows/agent_chat/graph.py` | messages ↔ research 桥 |
| `agent-chat-ui-main/.env` | `NEXT_PUBLIC_API_URL=http://localhost:2024` |
