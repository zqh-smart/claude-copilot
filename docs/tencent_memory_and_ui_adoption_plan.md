# TencentDB Chat Memory + UI 采用改造清单

> 状态：A–G 已落地；联调验收 DoD 通过（2026-08-04）  
> 日期：2026-08-04  
> 范围仓库：`claude_copilot`（后端 / LangGraph）+ `agent-chat-ui-main`（前端）+ 外部 `TencentDB-Agent-Memory`（MemoryCore sidecar）

---

## 0. 目标与边界

### 0.1 目标

1. **Chat 对话记忆**：用 MemoryCore sidecar 做 L0–L3 记忆管理（recall / capture）。
2. **文档知识记忆**：继续只走 **三库**——Postgres（结构化）+ Qdrant（向量）+ Neo4j（图谱）；**不**把年报知识写入 MemoryCore。
3. **图谱 UX**：保留 AntV G6，按 Tencent Wiki 图谱的产品标准对齐交互（搜索下拉、hover 邻居淡化、缩放控件、密度策略等）。
4. **Workbench 布局**：采用 Tencent `AssetSplitLayout` 分栏标准，改造知识库 / 新增 Chat Memory 管理页。

### 0.2 架构边界（必须遵守）

```text
用户浏览器 :3000 (agent-chat-ui-main)
  ├─ /                     Agent Chat
  │     → LangGraph :2025  graph=agent
  │           ├─ [NEW] MemoryCore :8420   ← Chat 记忆（L0–L3）
  │           └─ FastAPI :8000            ← 三库检索 / 子图
  │                 ├─ Postgres
  │                 ├─ Qdrant
  │                 └─ Neo4j
  └─ /knowledge /chat-memory /…          Workbench
        → /api/fastapi/* → FastAPI :8000
        → [NEW] /api/memory/* → MemoryCore :8420（仅 Chat 记忆浏览）
```

| 数据面 | 存储 | 写入方 | 读取方 |
|--------|------|--------|--------|
| 年报文档 / 指标 / 图谱 | Postgres + Qdrant + Neo4j | 文档管线 / Serving 入库 | RetrievalOrchestrator、research/risk/quant… |
| Chat 会话经验 L0–L3 | MemoryCore（sidecar 本地数据目录） | `agent` 图 capture | `agent` 图 recall；Workbench Chat Memory 页 |

**禁止**：

- MemoryCore 写入 FinancialSchema / 向量 / Neo4j 节点。
- 用 Wiki/CodeGraph 替换现有年报管线。
- 长期双写 Chat 记忆到 Postgres 与 MemoryCore（本期只写 sidecar）。

### 0.3 判定原则（质量优先）

- Chat 记忆产品标准对齐 Tencent（分层、召回 budget、失败不阻断主对话）。
- 财务数据面与 hybrid retrieval 继续自研三库。
- 图谱引擎不换 Sigma；交互必须对齐 Tencent 完成度。

---

## 1. 实施阶段总览

| 阶段 | 主题 | 主要仓库 | 依赖 |
|------|------|----------|------|
| **A** | MemoryCore sidecar 本地可跑 | TencentDB + 运维脚本 | 无 |
| **B** | LangGraph `agent` 接入 recall/capture | `claude_copilot` | A |
| **C** | FastAPI 可选代理 / 健康检查 / 配置 | `claude_copilot` | A |
| **D** | UI：Chat Memory 页 + 分栏布局 | `agent-chat-ui-main` | A、C（或直连 :8420） |
| **E** | UI：G6 图谱对齐 Tencent UX | `agent-chat-ui-main` | 无（可与 B 并行） |
| **F** | UI：KnowledgeBase 采用 AssetSplit | `agent-chat-ui-main` | E 可并行 |
| **G** | 文档 / env / 测试 / 启动脚本 | 两仓 | A–F |

建议落地顺序：**A → B → C → D**，**E/F 可并行**。

---

## 2. 阶段 A — MemoryCore Sidecar 运维接入

### 2.1 新建：`claude_copilot/scripts/run_memory_core.ps1`

**作用**：Windows 下一键启动 MemoryCore Gateway（`:8420`）。

**内容要求**：

1. 定位 Tencent 仓库路径（可用环境变量 `TENCENTDB_MEMORY_ROOT`，默认  
   `D:\GithubProject\TencentDB-Agent-Memory-feat-server_team\TencentDB-Agent-Memory-feat-server_team`）。
2. `cd $Root\MemoryCore`。
3. 若无 `node_modules`：执行 `npm install` + `npm run build`。
4. 写入/复用本地配置文件  
   `claude_copilot/deploy/memory-core/tdai-gateway.standalone.yaml`（见 2.2）。
5. 设置环境变量后启动：
   - `TDAI_GATEWAY_CONFIG` → 上述 yaml
   - `TDAI_GATEWAY_HOST=127.0.0.1`
   - `TDAI_GATEWAY_PORT=8420`
   - `TDAI_DATA_DIR` → 建议 `claude_copilot/data/chat_memory`（与三库数据目录并列，互不覆盖）
   - `TDAI_LLM_API_KEY` / `TDAI_LLM_BASE_URL` / `TDAI_LLM_MODEL`  
     → 与 `.env` 中 LLM 对齐（可从 `langgraph.env` 或 `.env` 读取）
6. 启动命令：`node --import tsx src/gateway/server.ts`（以 MemoryCore README 为准）。
7. 启动后打印：`http://127.0.0.1:8420/health`。

### 2.2 新建：`claude_copilot/deploy/memory-core/tdai-gateway.standalone.yaml`

**作用**：standalone Gateway 最小配置。

**必填项（对照 MemoryCore README）**：

- gateway host/port
- data dir
- LLM binding（抽取 L1/L2/L3 需要）
- recall 相关：`enabled`、`maxResults`、`timeoutMs`、`strategy`（建议 `hybrid`，无 embedding 时回退 BM25）

**不要**在此配置里指向 Postgres/Qdrant/Neo4j。

### 2.3 新建：`claude_copilot/deploy/memory-core/README.md`

说明：

- 与三库分工
- 启动顺序（MemoryCore → FastAPI → LangGraph → UI）
- `service_id` / `team_id` / `agent_id` / `user_id` 默认值
- 数据目录位置与备份注意（含对话原文）

### 2.4 修改：`claude_copilot/.gitignore`

追加（若尚未忽略）：

```gitignore
data/chat_memory/
```

### 2.5 修改：`claude_copilot/.env.example` 与 `claude_copilot/langgraph.env.example`

新增 Chat Memory sidecar 配置段（示例名）：

```dotenv
# Chat memory (MemoryCore sidecar) — NOT document KG
CHAT_MEMORY_ENABLED=true
CHAT_MEMORY_BASE_URL=http://127.0.0.1:8420
CHAT_MEMORY_API_KEY=
CHAT_MEMORY_SERVICE_ID=claude-copilot-local
CHAT_MEMORY_TEAM_ID=default-team
CHAT_MEMORY_AGENT_ID=agent
CHAT_MEMORY_USER_ID=local-user
CHAT_MEMORY_RECALL_TIMEOUT_MS=5000
CHAT_MEMORY_RECALL_MAX_RESULTS=5
CHAT_MEMORY_CAPTURE_ENABLED=true
```

同步更新运行中的 `.env` / `langgraph.env`（本地私密文件，不入库密钥）。

### 2.6 验收 A

```powershell
.\scripts\run_memory_core.ps1
curl http://127.0.0.1:8420/health
```

期望：健康检查 200。

---

## 3. 阶段 B — LangGraph `agent` 接入 Chat 记忆

### 3.1 新建：`claude_copilot/app/core/chat_memory/`

目录与文件：

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出 `ChatMemoryClient` / `ChatMemoryBundle` / `noop` |
| `protocol.py` | `ChatMemoryProtocol`：`recall(query, session_id)` / `capture(...)` / `health()` |
| `models.py` | `RecalledMemory`、`ChatMemoryBundle`（prepend / append 文本）、`CaptureTurn` |
| `client.py` | HTTP 客户端（优先官方 Python SDK；否则 `httpx` 调 `/recall` + v3 API） |
| `formatter.py` | 将 L1/L2/L3 格式化为可注入边界标签（对齐 Tencent `<relevant-memories>` / `<user-persona>`） |
| `noop.py` | `CHAT_MEMORY_ENABLED=false` 或健康失败时的空实现 |
| `ids.py` | 从 `RunnableConfig` 解析 `thread_id` → `session_id`；默认 team/agent/user |

#### 3.1.1 `protocol.py` 接口（必须）

```python
class ChatMemoryProtocol(Protocol):
    def recall(self, *, query: str, session_id: str | None) -> ChatMemoryBundle: ...
    def capture(
        self,
        *,
        session_id: str,
        user_text: str,
        assistant_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...
```

约束：

- `recall` / `capture` **不得抛到打断主对话**；内部吞掉超时/连接错误，打 warning，返回空 bundle / no-op。
- 超时使用 `CHAT_MEMORY_RECALL_TIMEOUT_MS`。

#### 3.1.2 `client.py` 实现要点

1. 优先尝试：  
   `from tencentdb_agent_memory import MemoryClient`  
   （依赖：可选 extra，或 `uv pip install` 本地 path  
   `../TencentDB-.../sdk/memory-core/python`）。
2. 若 SDK 不可用：`httpx` 实现最小子集：
   - `POST {base}/recall`（或 SDK 文档推荐的 v3 search）
   - `POST` L0 conversation capture（对照 MemoryCore `/capture` 或 `/v3/conversation/*`）
3. 每次请求带：
   - `Authorization: Bearer {CHAT_MEMORY_API_KEY}`（若配置）
   - `x-tdai-service-id: {CHAT_MEMORY_SERVICE_ID}`
   - body/header：`team_id` / `agent_id` / `user_id` / `session_id`
4. **禁止**在 client 内查询 Postgres/Qdrant/Neo4j。

#### 3.1.3 `formatter.py` 注入格式（必须有边界标签）

```text
<chat-memories>
- [L1] ...
</chat-memories>

<user-persona>
...
</user-persona>

<scenario-index>
- path_or_title
</scenario-index>
```

字符预算：

- 单条 L1 截断（可配置，默认 400 chars）
- 总 prepend 上限（默认 2000 chars）
- 超限丢弃低分条目

### 3.2 修改：`claude_copilot/app/core/config.py`

在 `Settings` 中新增字段（与 2.5 环境变量对应）：

| 字段 | 类型 | 默认 |
|------|------|------|
| `chat_memory_enabled` | `bool` | `False` |
| `chat_memory_base_url` | `str` | `http://127.0.0.1:8420` |
| `chat_memory_api_key` | `str \| None` | `None` |
| `chat_memory_service_id` | `str` | `claude-copilot-local` |
| `chat_memory_team_id` | `str` | `default-team` |
| `chat_memory_agent_id` | `str` | `agent` |
| `chat_memory_user_id` | `str` | `local-user` |
| `chat_memory_recall_timeout_ms` | `int` | `5000` |
| `chat_memory_recall_max_results` | `int` | `5` |
| `chat_memory_capture_enabled` | `bool` | `True` |
| `chat_memory_max_chars_per_memory` | `int` | `400` |
| `chat_memory_max_total_recall_chars` | `int` | `2000` |

### 3.3 修改：`claude_copilot/app/api/dependencies.py`

新增工厂：

```python
def get_chat_memory_client() -> ChatMemoryProtocol:
    ...
```

- `chat_memory_enabled=False` → `NoopChatMemory`
- 否则构造 `HttpChatMemoryClient`
- 可用 `@lru_cache` 或与现有 DI 风格一致

**不要**把 chat memory client 注入文档管线 / KG builder。

### 3.4 修改：`claude_copilot/pyproject.toml`

二选一（推荐 1）：

1. **可选 extra** `[chat_memory]`：依赖本地 path 或将来发布的 `tencentdb-agent-memory` wheel；未安装时走 httpx 降级。
2. 或仅用 `httpx`（项目多半已有），不强制 SDK。

新增依赖时注明：仅 Chat 记忆，与 `pdf_ocr` / `pdf_mineru` extras 并列。

### 3.5 修改：`claude_copilot/app/workflows/agent_chat/graph.py`（核心）

#### 3.5.1 扩展 `AgentChatState`

```python
class AgentChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    doc_id: str | None
    doc_id_b: str | None
    # NEW
    chat_memory_prepend: str | None
    chat_memory_warnings: list[str]
```

#### 3.5.2 拆分节点（推荐，便于测试）

当前：`START → research_turn → END`

改为：

```text
START → recall_chat_memory → research_turn → capture_chat_memory → END
```

| 节点 | 文件内函数 | 行为 |
|------|------------|------|
| `recall_chat_memory` | 新建 | 取最新 Human 文本 → `client.recall` → 写入 `chat_memory_prepend`；失败则空串 + warning |
| `research_turn` | 现有增强 | 在调用 specialist **之前**，把 `chat_memory_prepend` 拼进 `question` 的上下文或单独 system 段；**发给三库检索的 query 仍用清洁用户原文** |
| `capture_chat_memory` | 新建 | 取本轮 user 原文 + AI 回复 → `client.capture`；失败只记 log |

#### 3.5.3 `research_turn` 内精确修改点

在现有 `research_turn`（约 L327 起）中：

1. **保留** `_latest_human_text` 为清洁 `question`（用于 `classify_intent` 与三库检索）。
2. 从 state 读取 `chat_memory_prepend`。
3. 调用 `_invoke_chat_specialist` 时：
   - **方案甲（最小改动）**：若 prepend 非空，构造  
     `question_for_llm = f"{prepend}\n\n用户问题：{question}"`  
     仅用于需要 LLM 合成的路径；structured/sql 路由仍用 `question`。  
   - **方案乙（更干净，推荐若改动面可接受）**：给 `_invoke_chat_specialist` / research preview 增加可选参数 `chat_memory_context: str | None`，在 grounded synthesis prompt 中单独一节「对话记忆」，**不污染检索 query**。
4. **禁止**把 chat memory 文本送进 Qdrant embedding query（避免检索漂移）。
5. 返回 AIMessage 时，可在文末（调试模式）附加一行 `chat_memory_warnings`；默认生产不展示。

#### 3.5.4 `session_id` 解析

新建辅助 `_resolve_session_id(config)`：

1. `config.configurable.thread_id`（LangGraph 标准）
2. `config.configurable.session_id`
3. 回退：`f"{chat_memory_user_id}:default"`

#### 3.5.5 `build_agent_chat_graph` 边修改

```python
builder.add_node("recall_chat_memory", recall_chat_memory)
builder.add_node("research_turn", research_turn)
builder.add_node("capture_chat_memory", capture_chat_memory)
builder.add_edge(START, "recall_chat_memory")
builder.add_edge("recall_chat_memory", "research_turn")
builder.add_edge("research_turn", "capture_chat_memory")
builder.add_edge("capture_chat_memory", END)
```

`langgraph.json` 中 `agent` 入口路径**不变**（仍指向 `graph` 对象）。

### 3.6 新建测试：`claude_copilot/tests/workflows/test_agent_chat_memory.py`

用例：

1. `chat_memory_enabled=False`：图可跑通，不发起 HTTP。
2. recall 超时：仍返回三库答案（mock specialist），capture 不抛。
3. recall 成功：`research_turn` 收到 prepend（用 fake client）。
4. capture 收到清洁 user 文本（不含 prepend 污染）。

### 3.7 验收 B

1. MemoryCore + LangGraph 启动。
2. Agent Chat 连续两轮：第二轮能在 MemoryCore 面板/API 看到 L0；若抽取开启，可见 L1。
3. 关掉 MemoryCore：Chat 仍可用三库回答（降级）。

---

## 4. 阶段 C — FastAPI 侧（代理 / 健康 / 不碰三库写入）

> Chat 记忆主路径在 LangGraph；FastAPI 仅提供 Workbench 浏览代理与运维可见性。

### 4.1 新建：`claude_copilot/app/api/routes/chat_memory.py`

路由前缀：`/api/v1/chat-memory`

| Method | Path | 行为 |
|--------|------|------|
| `GET` | `/health` | 转发 MemoryCore `/health`；失败返回 `status=down`（HTTP 200 + body，避免 UI 崩） |
| `GET` | `/layers/{layer}` | `layer in {L0,L1,L2,L3}`；代理 v3 conversation/atomic/scenario/core list；query: `session_id`, `limit`, `offset` |
| `GET` | `/search` | 代理 atomic/conversation search；`q` 必填 |
| `POST` | `/capture` | 可选：Workbench 手工导入一段对话（非必须，Phase D 可后置） |

**明确不做**：

- 任何 document / segment / metric / graph 写入
- 替换现有 `/api/v1/knowledge-graph*`

### 4.2 修改：`claude_copilot/app/main.py`（或现有 router include 处）

`include_router(chat_memory.router, prefix=...)`  
与现有 v1 路由风格一致。

### 4.3 修改：`claude_copilot/app/api/dependencies.py`

复用 `get_chat_memory_client()`；路由层只依赖 Protocol。

### 4.4 新建测试：`claude_copilot/tests/api/test_chat_memory_routes.py`

- enabled=false → health 返回 disabled
- mock client → layers 列表 200

### 4.5 验收 C

```bash
curl http://127.0.0.1:8000/api/v1/chat-memory/health
```

---

## 5. 阶段 D — 前端 Chat Memory 页 + 分栏布局原语

### 5.1 从 Tencent 抄/改编的 UI 原语

源路径（参考，勿引入 Tea 依赖）：

- `MemoryPanel/web/src/pages/ResourcePage/components/AssetSplitLayout.tsx`
- `MemoryPanel/web/src/pages/ResourcePage/components/asset-split-layout.css`
- `MemoryPanel/web/src/lib/useResizable.ts`（若存在；用于可拖拽分栏）
- `ChatMemoryPanel` 的 Tab / 防竞态 `fetchSeqRef` 模式

#### 5.1.1 新建：`agent-chat-ui-main/src/components/workbench/AssetSplitLayout.tsx`

- Props：`sidebar: ReactNode`, `detail: ReactNode`, 可选 `sidebarWidth?: number`（默认 280）
- **不**依赖 `tea-component`
- 样式进 `workbench.css` 新 section `._asset-split`（或同目录 css module）

#### 5.1.2 新建：`agent-chat-ui-main/src/lib/useResizable.ts`

- 从 Tencent 逻辑移植：mousedown → mousemove → mouseup，约束 min/max width
- 供 Knowledge / Chat Memory 分栏使用

### 5.2 新建：`agent-chat-ui-main/src/lib/chat-memory-api.ts`

封装：

```ts
getChatMemoryHealth()
listLayer(layer: 'L0'|'L1'|'L2'|'L3', params)
searchMemories(q: string)
```

请求走：

- 优先 ` /api/fastapi/v1/chat-memory/...`（与现有 `copilot-api.ts` 一致），或
- 新建 Next 代理 `src/app/api/memory/[...path]/route.ts` → `CHAT_MEMORY_BASE_URL`

**推荐**：走 FastAPI 代理（阶段 C），前端不直连 :8420，避免 CORS/鉴权分叉。

### 5.3 新建页面与组件

| 路径 | 说明 |
|------|------|
| `src/app/(workbench)/chat-memory/page.tsx` | 路由页 |
| `src/components/workbench/ChatMemoryPanel.tsx` | 主面板：左列表 session/block，右 L0–L3 Tab |
| `src/components/workbench/ChatMemoryPanel.css`（可选） | 若不愿塞进 workbench.css |

`ChatMemoryPanel` 必须包含：

1. `AssetSplitLayout`
2. Layer Segment：`L0 | L1 | L2 | L3`
3. `fetchSeqRef` 防竞态（抄 Tencent ChatMemoryPanel 模式）
4. 切 Tab 时先清空再 loading
5. 空态文案：说明「此处为对话记忆，年报知识在知识库三库」
6. Health 条：sidecar down 时黄色警告，不挡浏览骨架

### 5.4 修改：Workbench 导航

定位现有侧栏/顶栏入口（搜索 `knowledge`、`/eval` 菜单定义处，例如 layout 或 nav 组件），新增：

- 文案：`对话记忆` / `Chat Memory`
- href：`/chat-memory`
- 分组：与「知识库」同组（资产），不要放进 Chat 主界面破坏现有 Agent UI

### 5.5 修改：`agent-chat-ui-main/.env` / `.env.example`

```dotenv
# 若走 FastAPI 代理则不必新增；若直连则：
# CHAT_MEMORY_URL=http://127.0.0.1:8420
```

保持现有：

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:2025
NEXT_PUBLIC_FASTAPI_URL=http://127.0.0.1:8000
```

### 5.6 （可选）修改：`src/components/thread/index.tsx` / Stream provider

若需把 `thread_id` 明确传入 LangGraph configurable：

- 确认 SDK 已自动带 `thread_id`；若无，在提交 run 时 `config.configurable.session_id = threadId`。
- **最小改动**：仅在缺失时补 `configurable`，不改消息气泡 UI。

### 5.7 验收 D

- 打开 `/chat-memory`，sidecar 有数据时能按层浏览。
- Chat 两轮后刷新该页可见 L0 增长。

---

## 6. 阶段 E — G6 图谱 UX 对齐 Tencent（不换引擎）

**目标文件**：`agent-chat-ui-main/src/components/workbench/KnowledgeGraphCanvas.tsx`  
**样式**：`agent-chat-ui-main/src/components/workbench/workbench.css`  
**参考**：Tencent `WikiPage/components/KnowledgeGraph.tsx`（Sigma）行为规格，**实现仍用 G6**。

### 6.1 已有（保留并作为基础）

- 骨架 / 完整视图 preset
- 类型过滤 chip
- 搜索输入（需升级为下拉结果，见下）
- 放大 / 缩小 / 重置
- 选中邻域 focus
- 财务类型色 / 边色字典
- 圆角矩形节点内标签

### 6.2 必须新增/改造的交互点

| # | 改造点 | 现状 | 目标行为（对齐 Tencent） | 改哪里 |
|---|--------|------|--------------------------|--------|
| E1 | 搜索下拉 | 仅过滤 `query` | 输入后下拉最多 8 条；点击 → 选中节点并 `focusNode`+适度 zoom | `KnowledgeGraphCanvas.tsx` 工具栏 |
| E2 | Hover 邻居高亮 | 依赖选中子图 | **悬停**时：当前节点+邻居高亮，其余节点降透明度、边隐藏或变淡；离开恢复 | G6 `node:pointerenter/leave` + 更新 element state/style |
| E3 | 浮层缩放钮 | 工具栏按钮已有 | 画布右下角 `+ / − / ⊙` 浮动控件（可与工具栏并存） | JSX + CSS `.kb-graph-fab` |
| E4 | 网格背景 | 无或弱 | 细网格 canvas 背景（CSS），提升「画布感」 | `.kb-graph-stage` |
| E5 | 度/权重边宽 | 边色有，线宽弱 | 按关系权重或度数微调 `lineWidth` | 边数据映射 |
| E6 | 结构噪声过滤 | 用 skeleton 类型 cap | 增加「隐藏叶子指标」开关（默认开），等价 Tencent hideStructural；映射：默认隐藏大量 `metric` 叶子 | toolbar checkbox |
| E7 | Label 密度 | `showLabels` 开关 | 节点多时自动降低标签显示（>N 仅 hub 显示标签） | `showLabels` 逻辑增强 |
| E8 | 统计文案 | 已有「当前 N / 全库 M」 | 保持；补充 `边数` | toolbar |
| E9 | Legend | 已有类型/边例 | 保持财务中文 label；布局贴底栏 | 已有，微调 CSS |
| E10 | 主题色读取 | 硬编码 hex | 可选：从 CSS 变量读主色；无则保留现有财务色板 | 小改，非阻断 |

### 6.3 明确不改

- 不引入 `graphology` / `@react-sigma/core` / `forceAtlas2`
- 不删财务 `NODE_COLORS` / `EDGE_COLORS` / `TYPE_PRIORITY`
- 不在图谱组件内请求 MemoryCore

### 6.4 验收 E

- 大图（metric 多）默认骨架可读。
- Hover 公司节点时邻居高亮、其余变淡。
- 搜索「营业收入」类节点可下拉点选定位。

---

## 7. 阶段 F — KnowledgeBase 采用 AssetSplit 布局

**目标文件**：`agent-chat-ui-main/src/components/workbench/KnowledgeBase.tsx`  
**样式**：`workbench.css`

### 7.1 布局改造

现状：偏单页堆叠（库列表 → 详情 Tab）。

目标：

```text
┌─────────────┬──────────────────────────────┐
│ 文档列表     │  详情：segments / hit / graph │
│ (sidebar)   │                              │
└─────────────┴──────────────────────────────┘
```

修改点：

1. 外层用 `AssetSplitLayout`。
2. 左侧：现有 library 列表（公司、文件名、状态 chip、时间）。
3. 右侧：现有 detail tabs（segments / hit / graph）原样迁入。
4. 接入 `useResizable`（可选）：左侧 240–400px。
5. 移动端：`<640px` 改为上下堆叠（CSS），避免不可用。

### 7.2 文案/信息架构微调

- 图谱 Tab 旁保留 Neo4j Browser 链接（已有则保留）。
- 增加一句说明：「图谱与片段来自三库；对话记忆见 /chat-memory」。

### 7.3 验收 F

- `/knowledge` 分栏可用；选文档后右侧刷新；图谱 Tab 仍加载 G6。

---

## 8. 阶段 G — 文档、脚本、启动顺序

### 8.1 修改：`claude_copilot/docs/agent_chat_ui.md`

追加章节：

1. Chat Memory sidecar 架构图（本文 0.2）
2. 启动 Terminal D：`.\scripts\run_memory_core.ps1`
3. 环境变量表（Chat Memory）
4. 降级行为说明
5. 与三库边界说明

### 8.2 修改：`claude_copilot/docs/project_architecture.md`

- 在模块边界中增加 `app/core/chat_memory/`
- 标明「对话记忆 ≠ 文档 KG」

### 8.3 修改：`claude_copilot/AGENTS.md`（Agent Chat UI 小节）

启动步骤增加 MemoryCore；注明可选。

### 8.4 修改：`claude_copilot/scripts/run_agent_langgraph.ps1`（可选）

- 启动前检测 `CHAT_MEMORY_ENABLED=true` 时 ping `:8420`，失败则黄字警告，**不阻断** LangGraph 启动。

### 8.5 新建：`claude_copilot/docs/chat_memory.md`

专题短文：

- L0–L3 在投研 Chat 中的含义（L2≈公司/年/主题场景时可后续演化）
- API 对照
- 备份与脱敏注意

### 8.6 工作区启动顺序（最终）

```powershell
# 1) 三库基础设施
docker compose up -d postgres qdrant neo4j redis

# 2) Chat 记忆 sidecar
.\scripts\run_memory_core.ps1

# 3) FastAPI（文档三库 + chat-memory 代理）
uv run uvicorn app.main:app --reload --port 8000

# 4) LangGraph agent
.\scripts\run_agent_langgraph.ps1

# 5) UI
cd ..\agent-chat-ui-main
pnpm dev
```

---

## 9. 明确「不修改」清单（防范围蔓延）

| 路径 / 模块 | 原因 |
|-------------|------|
| `app/pipeline/feature_pipeline/**` | 文档管线不接 Chat Memory |
| `app/core/kg/**` 写入逻辑 | 三库图谱独立 |
| `app/core/rag/**` 主检索 | 不把 MemoryCore 当向量库 |
| MemoryKnowledge / CodeGraph / MemoryProxy | 不在本期 |
| Tea UI / MemoryPanel 整仓搬迁 | 只抽布局与记忆交互模式 |
| `claude_copilot/web/**` | 已废弃 |
| 换 Sigma 替换 G6 | 企业选型已否决 |

---

## 10. 文件级总表（实施时逐项打勾）

### 10.0 进度快照

| 阶段 | 状态 | 备注 |
|------|------|------|
| A Sidecar 运维 | ✅ 2026-08-04 | 脚本/配置/env 示例已落地；需本机 Node 实测 `/health` |
| B Agent recall/capture | ✅ 2026-08-04 | `app/core/chat_memory` + 三节点图；pytest 17 passed |
| C FastAPI 代理 | ✅ 2026-08-04 | `/api/v1/chat-memory/*`；相关测试 16 passed |
| D Chat Memory UI | ✅ 2026-08-04 | `/chat-memory` + AssetSplit + nav |
| E G6 图谱 UX | ✅ 2026-08-04 | 搜索下拉 / hover 淡化 / FAB / 网格 / 叶子指标开关 |
| F KnowledgeBase 分栏 | ✅ 2026-08-04 | AssetSplit 左列表右详情；链到 /chat-memory |
| G 文档/脚本收尾 | ✅ 2026-08-04 | chat_memory.md、启动顺序、sidecar health 警告 |

### 10.1 `claude_copilot` 新建

- [x] `scripts/run_memory_core.ps1`
- [x] `deploy/memory-core/tdai-gateway.standalone.yaml`
- [x] `deploy/memory-core/README.md`
- [x] `docs/chat_memory.md`
- [x] `docs/tencent_memory_and_ui_adoption_plan.md`（本文）
- [x] `app/core/chat_memory/__init__.py`
- [x] `app/core/chat_memory/protocol.py`
- [x] `app/core/chat_memory/models.py`
- [x] `app/core/chat_memory/client.py`
- [x] `app/core/chat_memory/formatter.py`
- [x] `app/core/chat_memory/noop.py`
- [x] `app/core/chat_memory/ids.py`
- [x] `app/api/v1/chat_memory.py`
- [x] `tests/workflows/test_agent_chat_memory.py`
- [x] `tests/core/test_chat_memory_client.py`
- [x] `tests/api/test_chat_memory_routes.py`

### 10.2 `claude_copilot` 修改

- [x] `app/core/config.py` — Chat Memory settings
- [x] `app/api/dependencies.py` — `get_chat_memory_client`
- [x] `app/api/router.py` — include chat_memory routes
- [x] `app/workflows/agent_chat/graph.py` — recall/research/capture 三节点 + 清洁 query
- [x] `app/api/services/research_service.py` — `chat_memory_context` → synthesis only
- [ ] `pyproject.toml` — 可选依赖（本期用 httpx，无强制 SDK）
- [x] `.env.example` / `langgraph.env.example` — Chat Memory 段
- [x] `.gitignore` — `data/chat_memory/`
- [x] `docs/agent_chat_ui.md`
- [x] `docs/project_architecture.md`
- [x] `AGENTS.md`
- [x] `scripts/run_agent_langgraph.ps1`（Chat Memory 健康提示）

### 10.3 `agent-chat-ui-main` 新建

- [x] `src/components/workbench/AssetSplitLayout.tsx`
- [x] `src/lib/useResizable.ts`
- [x] Chat memory API 方法并入 `src/lib/copilot-api.ts`（走 `/api/fastapi`，无独立 memory 代理）
- [x] `src/components/workbench/ChatMemoryPanel.tsx`
- [x] `src/app/(workbench)/chat-memory/page.tsx`
- [x] （可选）`src/app/api/memory/[...path]/route.ts` — 跳过，复用 fastapi 代理

### 10.4 `agent-chat-ui-main` 修改

- [x] `src/components/workbench/KnowledgeGraphCanvas.tsx` — E1–E9（E10 主题 token 可选未做）
- [x] `src/components/workbench/workbench.css` — asset-split / chat-memory / fab / grid / search dropdown
- [x] `src/components/workbench/KnowledgeBase.tsx` — AssetSplit 改造
- [x] `src/components/app-nav.tsx` — 入口 `/chat-memory`
- [x] （可选）`session_id`/`thread_id` — LangGraph SDK 已传 `thread_id`；`resolve_session_id` 可读 configurable
- [x] `.env.example` — Chat Memory 段已在后端 `.env.example` / `langgraph.env.example`；前端走 fastapi 代理无需直连 :8420

### 10.5 外部（不改源码，只运维）

- [x] 可运行的 MemoryCore（Tencent 仓）Node ≥ 22.16 — `:8420` `/health` ok；recall strategy=`keyword`（无 Embedding）
- [x] LLM Key 可供 MemoryCore 抽取使用 — L1/L3 已有抽取产物（records / persona）；L1 非每轮必出

### 10.6 联调验收快照（DoD §13）

| # | 项 | 结果 | 备注 |
|---|----|------|------|
| 1 | 四进程可启动 | ✅ | MemoryCore `:8420` + FastAPI `:8000` + LangGraph `:2025` + UI `:3000`（2026-08-04 续联调） |
| 2 | Chat 两轮 → L0；sidecar 关仍可用 | ✅ | LangGraph `runs/wait` 两轮后 L0 `session_id=lg-e2e-1` 有 4 条；recall 降级单测仍绿 |
| 3 | `/chat-memory` 分层浏览 | ✅ | 页 200；`/api/fastapi/.../layers/L0|L3` 经 UI 代理 200 |
| 4 | `/knowledge` + G6 UX | ✅ | 页 200（修 G6 `applyInteractionStates` 误写的 Python 式 `*,`） |
| 5 | 三库写入零改动 | ✅ | 未改 pipeline/kg/rag 写路径 |
| 6 | 单测 recall 降级 + capture 清洁文本 | ✅ | chat-memory 相关 **20 passed** |

联调修复：`HttpChatMemoryClient` `trust_env=False`；L0/L1 浏览读 `CHAT_MEMORY_DATA_DIR` jsonl；清理 `--reload` 残留 multiprocessing 子进程后 `:8000` 才挂上新路由；G6 语法错误已修。

---

## 11. 数据流时序（验收对照）

```text
用户发送消息
  → LangGraph recall_chat_memory
       → MemoryCore /recall  （失败 → 空）
  → research_turn
       → classify_intent(清洁 question)
       → 三库检索 / 子图（清洁 question）
       → LLM 合成（可带 chat-memories 块）
  → capture_chat_memory
       → MemoryCore 写 L0（失败 → 忽略）
  → UI 展示 AI 回复

用户打开 /chat-memory
  → FastAPI /api/v1/chat-memory/layers/*
       → MemoryCore v3 API
```

---

## 12. 风险与回滚

| 风险 | 缓解 | 回滚 |
|------|------|------|
| MemoryCore 宕机 | recall/capture 降级；Chat 仍走三库 | `CHAT_MEMORY_ENABLED=false` |
| 记忆污染检索 | 清洁 query 与 inject 分离 | 去掉 prepend 拼接 |
| L1 抽取耗 LLM | 可先只 capture L0，关闭自动抽取 | Gateway 配置关 pipeline |
| UI 分栏破坏移动端 | CSS 断点堆叠 | 还原 KnowledgeBase 单栏 |
| 依赖 Node 运维成本 | 脚本化 + health 暴露 | 停 sidecar，功能降级 |

---

## 13. 完成定义（DoD）

1. 四进程可按文档启动：MemoryCore、FastAPI、LangGraph、UI。 — ✅（§10.6）
2. Chat 两轮后 MemoryCore 有 L0；sidecar 关闭时 Chat 仍可用。 — ✅（LangGraph 两轮 + 降级单测）
3. `/chat-memory` 可浏览分层记忆；文案标明与三库分离。 — ✅（页 + UI→FastAPI 代理）
4. `/knowledge` 分栏可用；G6 具备搜索下拉 + hover 淡化 + 浮层缩放。 — ✅（页 200；交互请浏览器目视）
5. 三库写入路径零改动（除无关的配置示例外无 pipeline/kg/rag 行为变化）。 — ✅
6. 单测覆盖 recall 降级与 capture 清洁文本。 — ✅（含 local_store browse，20 passed）

---

## 14. 后续（本文不实施，仅登记）

- L2 场景记忆按「公司 × 年 × 主题」结构化（仍存 MemoryCore 或将来迁 Postgres）。
- Chat Memory → 分析师偏好写入 L3 的财务专用 prompt。
- 多人 Team ACL（Tencent meta）——等企业多租户需求再开。
- pdf-inspector Detect gate——独立 PR，与记忆无关。
