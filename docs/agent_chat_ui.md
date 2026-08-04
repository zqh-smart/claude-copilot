# Agent Chat UI 对接说明

`agent-chat-ui-main` 是 **唯一前端**：Agent Chat + 知识库/工作台。Chat 需要 **LangGraph Server**（默认 `http://localhost:2025`），图 ID 为 `agent`；工作台经 `/api/fastapi` 代理访问 FastAPI `:8000`。

## 架构

```text
browser :3000 (agent-chat-ui-main)  — sole frontend
    ├─ /  Agent Chat
    │     → LangGraph API :2025  graph=agent
    │         → app/workflows/agent_chat/graph.py
    │             → recall_chat_memory → MemoryCore :8420   (Chat 记忆 L0–L3)
    │             → research_turn → 三库检索 / 子图
    │             → capture_chat_memory → MemoryCore
    └─ /knowledge /chat-memory /research /compare /reports /metrics /eval /jobs /upload
          → /api/fastapi/* → FastAPI :8000
                → documents / segments / knowledge-graph / research / eval …
                → /api/v1/chat-memory/* → MemoryCore :8420  (仅对话记忆浏览)

文档知识 = Postgres + Qdrant + Neo4j（三库）
对话记忆 = MemoryCore sidecar（与三库分离）

claude_copilot/web/:5173 已废弃，不再扩展。
```

## Chat Memory（可选 sidecar）

详见 [`docs/chat_memory.md`](./chat_memory.md) 与 [`deploy/memory-core/README.md`](../deploy/memory-core/README.md)。

| 项 | 说明 |
|----|------|
| 进程 | `.\scripts\run_memory_core.ps1` → `:8420` |
| 开关 | `CHAT_MEMORY_ENABLED=true`（`.env` + `langgraph.env`） |
| Agent 图 | `recall_chat_memory → research_turn → capture_chat_memory` |
| 降级 | sidecar 宕机或未启用时，Chat 仍走三库；仅无跨会话对话记忆 |
| UI | `/chat-memory`（非知识库；文案标明与三库分离） |

## 已注册 LangGraph 图

| 图 ID | 路径 | 说明 |
|-------|------|------|
| `agent` | `app/workflows/agent_chat/graph.py` | Agent Chat 入口；按 intent 路由子图 |
| `orchestrator` | `app/workflows/orchestrator/graph.py` | `classify_intent` + 混合检索编排 |
| `quant` | `app/workflows/quant/graph.py` | YoY / CAGR 等量化子图 |
| `risk` | `app/workflows/risk/graph.py` | HAS_RISK 检索 + 规则摘要 |
| `comparator` | `app/workflows/comparator/graph.py` | 双文档指标对比矩阵（P6h lite，无 UI） |
| `reporting` | `app/workflows/reporting/graph.py` | 单文档提纲报告（P6h lite，无导出） |
| `comparison_workflow` | `app/workflows/comparison_workflow/graph.py` | §5.4 lite：对比矩阵 + 风险对照 |
| `report_workflow` | `app/workflows/report_workflow/graph.py` | §5.5 lite：提纲 + Quant 快照（无 PDF） |

`research` 图（`app/workflows/research/graph.py`）存在但未注册于 `langgraph.json`；`agent` 经 `ResearchService.preview` 内联调用。

`comparator` / `reporting` 已挂入默认 `agent` 的 intent 路由（对比需第二 doc）。§6.2–6.4 产品面未做。

## Intent 路由

`orchestrator.classify_intent` 规则优先级（见 `app/workflows/orchestrator/graph.py`）：

| Intent | 触发示例 | Agent Chat 行为 |
|--------|----------|-----------------|
| `risk` | 市场风险、风险暴露 | 调用 `risk` 子图 |
| `compare` | 对比两家、比较营收 | 调用 `comparator`（需 `doc_id_b` / `AGENT_CHAT_DOC_ID_B`） |
| `quant` | 同比增长、CAGR | 调用 `quant` 子图 |
| `structured` | 某期营业收入是多少 | `ResearchService.preview` + 结构化前缀 |
| `report` | 生成提纲报告、写一份报告 | 调用 `reporting` 提纲子图 |
| `research` | 管理层展望、原因分析等 | `ResearchService.preview`（默认） |

502/超时时 Agent 仍返回结构化指标 + **混合检索摘要**（`fusion_summary`），不空答。

## 启动

```powershell
# Terminal 0 — 三库（文档知识）
docker compose up -d postgres qdrant neo4j redis

# Terminal A — Chat 记忆 sidecar（可选；CHAT_MEMORY_ENABLED=true 时需要）
.\scripts\run_memory_core.ps1
# → http://127.0.0.1:8420/health

# Terminal B — FastAPI（工作台 + chat-memory 代理）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Terminal C — LangGraph agent（Agent Chat 必需；Windows 推荐）
$env:PYTHONUTF8='1'
.\scripts\run_agent_langgraph.ps1
# → http://127.0.0.1:2025  graph id=agent
# 若 CHAT_MEMORY_ENABLED=true 且 :8420 不可达，脚本会黄字警告但不阻断

# Terminal D — UI（Chat + 工作台）
cd ..\agent-chat-ui-main
# .env: NEXT_PUBLIC_API_URL=http://localhost:2025
#       NEXT_PUBLIC_FASTAPI_URL=http://127.0.0.1:8000
pnpm install
pnpm dev
```

打开 http://localhost:3000 ：`/` = Chat（Assistant=`agent`）；`/knowledge` · `/chat-memory` 等 = 工作台。

Chat LLM 与 `.env` 对齐：`LLM_MODEL_API_TYPE=openai` + 本地 `192.168.0.102:30000`；embedding 仍用硅基。

## doc_id

优先顺序：

1. LangGraph `configurable.doc_id`
2. 环境变量 `AGENT_CHAT_DOC_ID`
3. 最新 `data/reports/serving_eval/*_serving_eval.json` 的 `doc_id`

## 文件

| 路径 | 作用 |
|------|------|
| `langgraph.json` | 注册 `agent` · `orchestrator` · `quant` · `risk` · `comparator` · `reporting` |
| `langgraph.env` | Agent 进程环境（与 `.env` 的 LLM/存储对齐；勿提交） |
| `app/workflows/agent_chat/graph.py` | messages ↔ recall/capture + orchestrator 路由桥 |
| `app/core/chat_memory/` | MemoryCore HTTP client（Chat 记忆，非文档 KG） |
| `app/api/v1/chat_memory.py` | Workbench 对话记忆代理 |
| `app/workflows/orchestrator/graph.py` | `classify_intent` 规则 |
| `scripts/run_memory_core.ps1` | 启动 MemoryCore sidecar |
| `agent-chat-ui-main/.env` | `NEXT_PUBLIC_API_URL` (LangGraph) + `NEXT_PUBLIC_FASTAPI_URL` (workbench) |
| `agent-chat-ui-main/src/app/(workbench)/*` | 知识库 / 对话记忆 / 研究 / 对比 / 报告 / BI / 评测 / 任务 / 上传 |
| `agent-chat-ui-main/src/app/api/fastapi/[...path]/route.ts` | FastAPI 同源代理 |
