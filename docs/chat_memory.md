# Chat Memory（MemoryCore Sidecar）

对话记忆与文档知识是两条线：

| 面 | 存储 | 用途 |
|----|------|------|
| **Chat 记忆** | MemoryCore sidecar（`data/chat_memory/`） | L0 对话 · L1 原子事实 · L2 场景 · L3 画像 |
| **文档知识** | Postgres + Qdrant + Neo4j | 年报解析、指标、检索、财务图谱 |

**禁止**把年报 / FinancialSchema / 向量 / Neo4j 节点写入 MemoryCore。

## 架构

```text
Agent Chat (LangGraph :2025)
  recall_chat_memory → research_turn → capture_chat_memory
         │                    │                  │
         ▼                    ▼                  ▼
   MemoryCore :8420     三库检索/子图      MemoryCore L0
         │
Workbench /chat-memory
  → FastAPI /api/v1/chat-memory/*
       → MemoryCore
```

- 检索 / intent 使用**清洁用户问题**（不含记忆文本）。
- `chat_memory_context` 仅注入 research **合成**路径（`ResearchService.preview(..., chat_memory_context=...)`）。
- recall / capture **失败不打断**主对话（降级为空记忆）。

## 启动

```powershell
# 1) 可选但推荐：Chat 记忆 sidecar
.\scripts\run_memory_core.ps1
# → http://127.0.0.1:8420/health

# 2) FastAPI（含 /api/v1/chat-memory 代理）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# 3) LangGraph agent
.\scripts\run_agent_langgraph.ps1

# 4) UI
cd ..\agent-chat-ui-main
pnpm dev
```

详见 `deploy/memory-core/README.md`。

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `CHAT_MEMORY_ENABLED` | `false` | 总开关；false 时用 Noop |
| `CHAT_MEMORY_BASE_URL` | `http://127.0.0.1:8420` | MemoryCore |
| `CHAT_MEMORY_API_KEY` | 空 | 非回环部署时建议设置 |
| `CHAT_MEMORY_SERVICE_ID` | `claude-copilot-local` | `x-tdai-service-id` |
| `CHAT_MEMORY_TEAM_ID` / `AGENT_ID` / `USER_ID` | `default-team` / `agent` / `local-user` | v2/v3 隔离字段 |
| `CHAT_MEMORY_RECALL_TIMEOUT_MS` | `5000` | 召回超时 |
| `CHAT_MEMORY_CAPTURE_ENABLED` | `true` | 是否写 L0 |
| `TENCENTDB_MEMORY_ROOT` | 见脚本默认 | Tencent 仓根目录（含 `MemoryCore/`） |

同时写入 `.env` 与 `langgraph.env`（agent 进程读后者）。

## API（FastAPI 代理）

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/chat-memory/health` | sidecar 状态；disabled 也 200 |
| GET | `/api/v1/chat-memory/layers/{L0\|L1\|L2\|L3}` | 分层浏览 |
| GET | `/api/v1/chat-memory/search?q=` | 搜索 |
| POST | `/api/v1/chat-memory/capture` | 手工写入一轮 |

前端：`agent-chat-ui-main` → `/chat-memory`（经 `/api/fastapi`）。

## 投研语义映射（后续可深化）

| MemoryCore | Claude Copilot 含义 |
|------------|---------------------|
| L0 | 会话原文 |
| L1 | 偏好、已确认口径、短结论 |
| L2 | 公司 × 年 × 主题 场景卡（可演进） |
| L3 | 分析师偏好简档 |

## 备份与脱敏

- 数据目录：`data/chat_memory/`（gitignore）
- 含对话原文，导出/分享前需脱敏
- 与 Postgres / Qdrant / Neo4j 数据目录分离

## 相关代码

| 路径 | 作用 |
|------|------|
| `app/core/chat_memory/` | HTTP client / noop / formatter |
| `app/workflows/agent_chat/graph.py` | recall → research → capture |
| `app/api/v1/chat_memory.py` | Workbench 代理 |
| `scripts/run_memory_core.ps1` | 启动 sidecar |
| `docs/tencent_memory_and_ui_adoption_plan.md` | 完整改造清单 |
