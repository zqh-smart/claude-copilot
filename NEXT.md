# 当前下一步

> 写于 2026-09-16。这是仓库根上的执行顺序，不是架构讨论稿。
> 详细接线见 [`frontend/apps/chat-ui/RUNTIME.md`](frontend/apps/chat-ui/RUNTIME.md)。
> 产品边界见 [`frontend/ARCHITECTURE.md`](frontend/ARCHITECTURE.md)。

## 一句话

**架构已冻结。下一步不是加功能，而是把 chat-ui 的 15 项 P0 验收跑绿。绿之前禁止 Tool UI / Generative UI / HITL。**

两套前端都还在，不要把 chat 当成整个产品：

| 应用 | 地址 | 职责 |
| --- | --- | --- |
| `frontend/apps/workbench` | `http://127.0.0.1:3000/` | 知识库 / 研究 / 对比 / 报告 / 指标 / 评测 / 任务 / 上传 / 对话记忆 |
| `frontend/apps/chat-ui` | `http://127.0.0.1:3001/chat/` | 完整 Agent 对话（线程、流式、取消），对接 LangGraph `:2025` |

工作台打开 Agent Chat 时只交接 `cc_source` / `cc_resource` / `cc_prompt`，不把文档正文或密钥塞进 URL。

## 现在卡在哪

`RUNTIME.md` 里 Run 1 日志已经过时。以本文件为准。

| # | 项 | 状态 | 说明 |
| --- | --- | --- | --- |
| 1 | `pnpm build` | PASS | chat-ui + workbench 都能生产构建 |
| 2 | `pnpm typecheck` | PASS | contracts / workbench / chat-ui 干净 |
| 3 | `/chat/` 能打开 | PASS | 尾斜杠是硬合同：`/chat` 404，`/chat/` 200 |
| 4 | 工作台交接 `cc_*` | 代码已接，e2e 未在干净 `:3000` 上跑通 | `setChatLaunchContext` + `__CHAT_UI_URL__` 已落地；本机 `:3000` 曾被 Cursor/Gitea 占用 |
| 5 | 点「新对话」建线程 | **判定标准已改** | `react-langgraph` 0.14.28 在**首条消息发送时**才 `initialize()`，点「新对话」本身不打 `POST /threads` |
| 6 | 线程列表来自 `:2025` | PASS | 侧栏能显示 `client.threads.search` 的结果 |
| 7 | 切换线程消息不丢 | 未跑 | 需要真实 LLM 往返 |
| 8 | F5 消息还在 | 未跑 | 需要真实 LLM 往返 |
| 9 | 流式 token | 未跑 | `langgraph.env` 里 LLM key 为空 |
| 10 | Stop 停掉 UI 流 | 未跑 | 同 9 |
| 11 | `:2025` 挂了要有限错误 | **FAIL（冷启动）** | 发送后 Stop 一直在、无 toast、无 alert，`isRunning` 不落。这是硬门 |
| 12 | `:2025` 挂了不挡壳 | 壳能渲染 | 「打开已有线程」半边还没测 |
| 13 | 线程隔离 | 未跑 | 需要真实 LLM 往返 |
| 14 | F5 保留 launch context 且不重发 prompt | PASS（banner 半边） | 横幅和 `cc_*` 能活过 F5；「线程也回来」需要已有远程线程 |
| 15 | Stop 真取消服务端 run | 未跑 | 需要真实 LLM 往返 |

旧 chat-ui（Next.js）里的 HITL / 工具调用 / 附件 / 代码高亮已从工作区删掉，**代码仍在 git `44f1ff8`**，P1 以后按需取回参考，现在不要恢复。

## 必须按这个顺序做

### 0. 本地端口合同（每次开工会先核对）

```text
:3000  工作台（必须是 Vite workbench，不能是别的转发）
:3001  chat-ui，且 URL 是 /chat/
:8000  FastAPI
:2025  LangGraph  in-memory（scripts/run_agent_langgraph.ps1）
```

本机曾出现 `:3000` 被 Cursor 端口转发占成 Gitea 的情况。那种状态下不要跑交接 e2e，先把端口腾出来。

启动 LangGraph：

```powershell
cd backend
$env:PYTHONUTF8 = '1'
.\scripts\run_agent_langgraph.ps1
```

Windows 上 `langgraph-cli` 缺 `colorama` 会在绑端口前崩掉；`pyproject.toml` 的 `langgraph_api` extra 已经带上了。LLM key 仍要自己填进 `backend/langgraph.env`（gitignored）。

### 1. 修验收 #11（当前唯一前端硬缺陷）

冷启动、`:2025` 未起来时点发送：

- 失败发生在 `POST /threads`（`threadListAdapter.initialize`），**进不了** run queue 的 reject 路径
- `thread.isRunning` 不落 → Stop 按钮一直在
- `ChatToaster` 已挂载但从没被调用；`useLangGraphRuntime` **没有** `onError`

要做的事：

1. 查 `@assistant-ui/core` 0.15 / `react-langgraph` 0.14.28 里 `AssistantError` / `ErrorDisplay` 的订阅点，不要手写 SSE
2. 让 `initialize()` 失败变成有限错误（toast 或 inline），并清掉 `isRunning`
3. 用 `LANGGRAPH_DOWN=1 pnpm test:e2e` 跑 `frontend/e2e/p0-resilience.spec.ts`（断言已经改严，旧版「页面有字就算过」作废）
4. 补测中途挂掉：先有线程再杀 `:2025`，再发送——这是另一条代码路径

#11 不过，后面全部停。

### 2. 在干净端口上关闭 #4

1. 确认 `http://127.0.0.1:3000/` 返回工作台（HTML 里有 `id="app"`），不是 Gitea
2. 跑 `frontend/e2e/handoff-acceptance.spec.ts`
3. 从 `/knowledge` 点 Agent Chat，URL 必须落到 `http://127.0.0.1:3001/chat/?cc_source=knowledge&cc_resource=…&cc_prompt=…`，chat-ui 顶栏出现「已从工作台衔接」

### 3. 填 LLM key，跑需要往返的项

`backend/langgraph.env` 填 `LLM_MODEL_API_KEY` / `SILICON_KEY`（按你实际后端）。然后按这个顺序人工 + e2e：

1. **#5 按真实合同重测**：点「新对话」不建远程线程；发第一条消息后 `?thread=<uuid>` 出现，且 `client.threads.search` 能搜到
2. **#7 / #8 / #13**：线程 A 发 3 条 → 切 B → 切回 A；F5 后 A/B 都在；状态不串
3. **#9 / #10 / #15**：能看到增量 delta；点 Stop 后 UI 停、`:2025` 上 run 真的 cancel、下一条还能流

把结果追加到 `RUNTIME.md` 的 acceptance run log，不要覆盖本文件的顺序。

### 4. P0 全绿之后才进入 P1

顺序锁死，与 `RUNTIME.md` §Next rounds 一致：

| 优先级 | 做什么 | 不要做什么 |
| --- | --- | --- |
| P1 | `search_financial_report` 的 Tool UI（工具执行 → 片段 → Citation → PDF 页码） | 不要先做 Generative UI |
| P1 | Citation 面板（LangGraph `metadata` → 文内 `[C#]`） | 不要把引用逻辑写进 workbench |
| P2 | HITL：把 `interrupt` 做成审批卡（可参考 `44f1ff8` 里旧 `agent-inbox`） | 不要把 HITL 嵌进 Vue |
| P2 | 消息体内联财务表 / 图 | 不要换 runtime |
| P3 | 附件接到后端上传 | 不要在 P0 假装已有附件 UI（当前 Composer **没有**附件占位） |

任何 `@assistant-ui/*` 升级都必须把 15 项重跑一遍。

## 明确不做

- 不再改框架：不回 Next.js、不上 `@assistant-ui/react-langchain` 当主 runtime、不手写 `ChatModelAdapter` / SSE 解析
- 不把 React 组件搬进 Vue，也不把 Vue 页面搬进 chat-ui
- 不在 `backend/web/` 加产品 UI
- 不为了「看起来完整」把旧 agent-inbox / 附件代码整包拷回来；P1 按一条工具链路重接

## 相关文件

| 文件 | 用途 |
| --- | --- |
| `frontend/apps/chat-ui/RUNTIME.md` | 15 项验收原文、版本钉死、流式/线程缝 |
| `frontend/e2e/chat-p0.spec.ts` | #3 / #5 合同 / #6 / #14 |
| `frontend/e2e/p0-resilience.spec.ts` | #11 / #12，必须 `LANGGRAPH_DOWN=1` |
| `frontend/e2e/handoff-acceptance.spec.ts` | #4 工作台 → chat 往返 |
| `frontend/e2e/workbench-surface.spec.ts` | 10 个工作台路由还在 |
| `frontend/apps/workbench/src/lib/chat-launch-context.ts` | 当前页把资源交给顶栏 |
| `backend/scripts/run_agent_langgraph.ps1` | `:2025` 启动（含 Windows colorama extra） |
