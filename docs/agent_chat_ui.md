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

打开 http://localhost:3000/chat ：Chat（Assistant=`agent`）；`/` 是首页概览，`/knowledge` · `/chat-memory` 等为工作台。

Chat LLM 与 `.env` 对齐：`LLM_MODEL_API_TYPE=openai` + 本地 `192.168.0.102:30000`；embedding 仍用硅基。

## doc_id

优先顺序：

1. 消息提交的 state `doc_id`（Chat 顶部选择已处理完成的财报）
2. LangGraph `configurable.doc_id`
3. 环境变量 `AGENT_CHAT_DOC_ID`
4. 最新 `data/reports/serving_eval/*_serving_eval.json` 的 `doc_id`

## 按消息保存研究结果

`research` / `structured` 分支复用本次 `ResearchService.preview`，不为侧栏重复检索。
AI 消息的 `additional_kwargs.research_result` 保存 `ChatResearchResult`：

- `schema_version: 1`、`thread_id`、`request_message_id`：关联会话及产生该答案的问题。
- `previews: ResearchPreviewResponse[]`：完整研究快照，含文档、指标、证据、引用、审核结果及警告；次级研究分支也保留自己的结果。

前端只显示当前会话最新答案、且问题消息 ID 匹配的快照。发出新问题、切换财报、请求失败时不回退展示上一条证据。历史消息没有快照时显示空态，不从答案文本猜测引用。刷新后从 LangGraph 消息历史恢复，不依赖前端临时缓存。

引用区区分“答案引用”和“检索证据”。`Vn` 指向文档片段，`Sn` 指向结构化指标；指标使用其自身 `document_id`，不能直接套用当前财报 ID。页码仅取返回的来源元数据，缺少页码时打开原文。暂不能定位文档来源的 `Cn` / `Gn` 引用明确标记，不生成虚假链接。纯 risk / compare / quant / report 分支尚未提供统一研究快照，侧栏为空。

原文接口：`GET /api/v1/documents/{doc_id}/source`。仅返回文档记录关联且位于配置归档目录内的文件；记录缺失、文件缺失或越界均返回 404。PDF 内联查看，其他格式作为附件下载。同源 FastAPI 代理保留 `Content-Disposition`、`Cache-Control` 和 `X-Content-Type-Options`。该接口沿用现有 API 访问模型，并非新增多租户授权层。

验证：

```powershell
uv run pytest tests/test_agent_chat_graph.py tests/workflows tests/api/services/test_research_service.py tests/test_documents.py tests/core/rag -q
uv run python scripts/run_stage_eval.py --compare-baseline --output data/reports/eval/chat_integration_scorecard.json

cd ../agent-chat-ui-main
pnpm exec tsc --noEmit --incremental false
# 如 :3000 已运行，可复用服务，避免两个 Next dev 进程共享 .next
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3000'
pnpm test:e2e
```

浏览器测试使用隔离的 API / LangGraph 响应夹具，覆盖 `/chat` 入口、财报选择、流式结果绑定、刷新、切换会话和失败空态。这些测试不代替真实三库、模型和财报的完整联调。

### 本轮验收记录（2026-08-27）

- 上述后端相关回归：84 passed；浏览器隔离测试：5 passed；TypeScript 和修改文件的 Prettier 检查通过。
- 指南针 2021 财报阶段评测：`core_metric_exact_match=1.0`、`source_grounding_rate=1.0`，与已有基线持平；Serving gate 通过。报告在 `data/reports/eval/chat_integration_scorecard.json`。整体对比为 `mixed`：解析吞吐量降低、小切片比例从 0.0097 升到 0.0126，不能据此宣称性能提升。
- 前端 `/chat`、FastAPI `/health`、LangGraph `/info` 返回 200；文档列表请求超时。Docker Desktop 因本机运行时 socket 访问错误未恢复，三库真实财报完整联调仍待验收。未重置数据库卷、修改模型或替换框架。
- 全量 pytest 尝试未完成；依赖数据库的接口测试仍受运行环境影响，不能将上述相关回归结果当作全量通过。
- 后续已增加 `@live` 真实联调入口（命令见 `docs/acceptance_suite.md` §0）并实际执行：文档 API 在 10 秒前置检查中超时，尚未进入模型提问。失败 trace 保存为 `data/reports/chat_live_preflight_20260827.zip`。
- 停止残留 Docker 进程后，Windows 仍拒绝重命名 `docker-secrets-engine` 运行时目录，未修改权限或重置卷。Docker 官方问题库有相同故障报告：[残留 socket 导致启动失败](https://github.com/docker/desktop-feedback/issues/460)。当前需用户在本机重启 Windows、再启动 Docker 后复验；这不是数据库已恢复的证明。

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
