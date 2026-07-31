# Agent Chat UI 对接说明

`agent-chat-ui-main` 需要 **LangGraph Server**（默认 `http://localhost:2025`），图 ID 为 `agent`（`messages` state）。

## 架构

```text
browser :3000 (agent-chat-ui)
    → LangGraph API :2025  graph=agent
        → app/workflows/agent_chat/graph.py
            → orchestrator.classify_intent(question)
                → risk       → app/workflows/risk/graph.py
                → quant      → app/workflows/quant/graph.py
                → structured → ResearchService.preview（结构化指标前缀）
                → research   → ResearchService.preview（默认投研）
                    → Postgres / Qdrant / LLM（.env / langgraph.env）
```

内部工作台 `web/:5173` 仍直连 FastAPI `:8000`（文档 / L3），不经过本桥。

## 已注册 LangGraph 图

| 图 ID | 路径 | 说明 |
|-------|------|------|
| `agent` | `app/workflows/agent_chat/graph.py` | Agent Chat 入口；按 intent 路由子图 |
| `orchestrator` | `app/workflows/orchestrator/graph.py` | `classify_intent` + 混合检索编排 |
| `quant` | `app/workflows/quant/graph.py` | YoY / CAGR 等量化子图 |
| `risk` | `app/workflows/risk/graph.py` | HAS_RISK 检索 + 规则摘要 |
| `comparator` | `app/workflows/comparator/graph.py` | 双文档指标对比矩阵（P6h lite，无 UI） |
| `reporting` | `app/workflows/reporting/graph.py` | 单文档提纲报告（P6h lite，无导出） |

`research` 图（`app/workflows/research/graph.py`）存在但未注册于 `langgraph.json`；`agent` 经 `ResearchService.preview` 内联调用。

`comparator` / `reporting` **不**挂到默认 `agent` 对话路由（对比需 `doc_id_a`+`doc_id_b`）；在 Agent Chat 或 LangGraph Studio 中直选图 ID 调试。§6.2–6.4 产品面未做。

## Intent 路由

`orchestrator.classify_intent` 规则优先级（见 `app/workflows/orchestrator/graph.py`）：

| Intent | 触发示例 | Agent Chat 行为 |
|--------|----------|-----------------|
| `risk` | 市场风险、风险暴露 | 调用 `risk` 子图 |
| `quant` | 同比增长、CAGR | 调用 `quant` 子图 |
| `structured` | 某期营业收入是多少 | `ResearchService.preview` + 结构化前缀 |
| `research` | 管理层展望、原因分析等 | `ResearchService.preview`（默认） |

502/超时时 Agent 仍返回结构化指标 + **混合检索摘要**（`fusion_summary`），不空答。

## 启动

```powershell
# Terminal A — FastAPI（可选，工作台用）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Terminal B — LangGraph agent（Agent Chat 必需；Windows 推荐）
$env:PYTHONUTF8='1'
.\scripts\run_agent_langgraph.ps1
# → http://127.0.0.1:2025  graph id=agent
# 可用 $env:LANGGRAPH_PORT='2024' 覆盖端口

# Terminal C — UI
cd ..\agent-chat-ui-main
pnpm install
pnpm dev
```

打开 http://localhost:3000 ，Deployment URL=`http://localhost:2025`，Assistant=`agent`（默认）。亦可直选 `orchestrator` / `quant` / `risk` / `comparator` / `reporting` 做专项调试。

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
| `app/workflows/agent_chat/graph.py` | messages ↔ orchestrator 路由桥 |
| `app/workflows/orchestrator/graph.py` | `classify_intent` 规则 |
| `agent-chat-ui-main/.env` | `NEXT_PUBLIC_API_URL=http://localhost:2025` |
