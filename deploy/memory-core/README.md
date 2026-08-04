# MemoryCore Chat Memory Sidecar

Claude Copilot 用 MemoryCore（TencentDB Agent Memory）做 **Chat 对话记忆**（L0–L3）。  
**年报 / 指标 / 图谱** 仍只走 Postgres + Qdrant + Neo4j，互不写入。

## 分工

| 面 | 存储 | 用途 |
|----|------|------|
| Chat 记忆 | MemoryCore（本 sidecar，`data/chat_memory/`） | 会话、偏好、跨轮结论 |
| 文档知识 | Postgres / Qdrant / Neo4j | 解析入库、检索、财务 KG |

## 要求

- Node.js `>= 22.16`
- 本机可访问的 OpenAI-compatible LLM（L1/L2/L3 抽取需要；只读 recall 可无有效 key，但 capture 沉淀会弱）
- 源码根：环境变量 `TENCENTDB_MEMORY_ROOT`，默认  
  `D:\GithubProject\TencentDB-Agent-Memory-feat-server_team\TencentDB-Agent-Memory-feat-server_team`

## 启动

```powershell
# 在 claude_copilot 根目录
.\scripts\run_memory_core.ps1
# → http://127.0.0.1:8420/health
```

建议完整顺序：

1. `docker compose up -d postgres qdrant neo4j redis`
2. `.\scripts\run_memory_core.ps1`
3. FastAPI `:8000`
4. LangGraph `:2025`
5. `agent-chat-ui-main` `:3000`

## 默认隔离 ID（与 `.env` 对齐）

| 变量 | 默认 | 含义 |
|------|------|------|
| `CHAT_MEMORY_SERVICE_ID` | `claude-copilot-local` | Memory space（`x-tdai-service-id`） |
| `CHAT_MEMORY_TEAM_ID` | `default-team` | v3 team |
| `CHAT_MEMORY_AGENT_ID` | `agent` | 对应 LangGraph graph id |
| `CHAT_MEMORY_USER_ID` | `local-user` | 单用户本地 |

## 数据与备份

- 目录：`claude_copilot/data/chat_memory/`（已 gitignore）
- 含对话原文，分享前需脱敏
- **不要**把该目录配成 Postgres/Qdrant/Neo4j 数据路径

## 降级

`CHAT_MEMORY_ENABLED=false` 或 sidecar 宕机时：Agent Chat 仍走三库检索，仅无跨会话对话记忆。
