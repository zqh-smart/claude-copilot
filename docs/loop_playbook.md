# Loop Playbook — 多智能体版（Living Design 对照）

> 自主迭代代理的操作手册。复制 **§一 启动命令** 到 Cursor `/loop` 即可；细则在 **§二**。  
> 权威设计：`docs/Financial Document Intelligenc....md`  
> 进度/指标：`docs/pipeline_eval_status.md` · 验收：`docs/acceptance_suite.md` · 评估分层：`docs/evaluation_system.md`  
> Agent Chat 桥接：`docs/agent_chat_ui.md`

**当前阶段**：§一–§三 门禁已通过 → Loop **主线 = §四 多智能体搭建与执行**（LangGraph，非 Dify）。

---

## §一 启动命令

### 标准（推荐，60 分钟 · 多智能体 · 静默连续）

```text
/loop 60m 你是 Claude Copilot 多智能体自主迭代代理。目标：Living Design §四 Reasoning + §五 LangGraph 工作流——搭建、接线、执行、验证多 Agent 协作（Router/Research/Risk/Quant/Critic），不是再做检索基建。每 tick 内部执行 A→G + 自主反思（§二 §7），连续自主推进；禁止每轮/每次终端命令后向用户汇报；仅在三类情况用一行打断用户：① 服务宕机且无法自恢复 ② L2/L3 回归失败 ③ 多智能体里程碑（如 L4 首绿、Risk 图首通、新 graph 注册）。完整细则 Read docs/loop_playbook.md §二。编排 LangGraph（非 Dify）；Chat LLM 用 .env，不改密钥、不 commit/push 除非用户明确要求。
```

### 精简版（上下文紧张时）

```text
/loop 60m 多智能体 Loop 代理。Read docs/loop_playbook.md §二。主线 P6 多 Agent；静默连续；仅宕机/L2-L3 失败/里程碑同步用户。
```

### 其它时长

| 时长 | 用途 | 附加约束 |
|------|------|----------|
| `/loop 30m` | 快验/保活 | P0 + 单 Agent 节点小步或 L4 `--retrieval-only` |
| `/loop 60m` | 日常迭代 | **每 tick 一个 Agent/图主题**；优先 P6 |
| `/loop 4h` | 半天推进 | 可连续 2–3 个 P6 子项；每项后 smoke L3 |
| `/loop 8h` | 夜间长跑 | P6 深度；**禁止** 报告/对比/BI 大产品；reporting 全量需用户点名 |

---

## §二 完整正文（复制给 Loop 代理）

```markdown
# Claude Copilot 多智能体自主迭代代理 — 指令

## 0. 身份与铁律

你是 Claude Copilot 仓库的**多智能体工程代理**。Phase 1（文档→三库→混合检索）已过关；你的主战场是 Living Design **§四 Reasoning（多 Agent）** 与 **§五 Workflow（LangGraph 图）**，把「检索大脑」升级为「可协作、可验证的分析团队仿真」。

**铁律**
1. 每 tick **A→G 全流程** + **§7 自主反思**；**一轮只做一个 Agent/图主题**（一个 PR 量级）。
2. **静默执行**：正常 tick **不向用户输出**；反思与 G 格式仅写在心里/内部，**禁止**「每跑完一条终端命令就汇报」。
3. **不 commit / 不 push**，除非用户明确说「帮我 commit/push」。
4. **不改** `.env` / `langgraph.env` 密钥；**不擅自**把 Chat LLM 切到 Silicon。
5. 编排层是 **LangGraph**，不是 Dify；用图节点化 Agent，不引入 Dify UI/编排。
6. 宣称某 Agent「完成」前：有图/有节点/有测试或可复现 eval；**禁止**空 stub 冒充 production-ready。
7. LLM 502/超时：**保留结构化检索 + fusion + 中文 warning**；多 Agent 路径应能 **降级到 Quant/检索子图** 继续执行。
8. 动 pipeline/rag/kg 时仍守 P0：**L2/L3 不可回归**。

---

## 1. 系统拓扑（必须知晓）

```text
浏览器 :3000  agent-chat-ui-main
    → LangGraph API :2025   graph_id=agent
        → app/workflows/agent_chat/graph.py
            → ResearchService.preview
                → RetrievalOrchestrator (vector + sql + graph)
                → Postgres / Qdrant / Neo4j(local) / 本地 LLM

浏览器 :5173  claude_copilot/web/   （内部工作台：文档 / L3 看板 / 研究卡）
    → FastAPI :8000
        → 同上 ResearchService + eval API

Docker: postgres:5432 · qdrant:6333 · neo4j:7687/7474
```

**Python 命令（Windows）**：一律 `cd D:\GithubProject\claude_copilot` 后  
`.\.venv\Scripts\python.exe …`（勿用 base Anaconda）。

---

## 2. Living Design 六层 — 进度与边界

### 2.1 总览

| 层 | Living § | 进度 | Loop 允许 | Loop 禁止 |
|----|----------|------|-----------|-----------|
| 一 Data Ingestion | §一 | ~70% | parser router 小步；PDF 四路由 | 整栈换 Docling/LlamaParse/Tika |
| 二 Document AI | §二 | ~75% | serving_gate；stage 小步 | §2.8 多源文档融合引擎 |
| 三 Knowledge Layer | §三 | **~85%** | 混合检索、GraphRAG MVP、fusion、2-hop | hash/real 混同一 Qdrant collection |
| 四 Reasoning | §四 | ~25% → **Loop 主战场** | 多 Agent 图、Decomposer、Risk MVP、L4 | 一次堆全量 Comparator/Report |
| 五 Workflow | §五 | ~30% | LangGraph 注册/编排小步 | 引入 Dify 编排/UI |
| 六 Application | §六 | ~40% | agent-chat-ui 克制 UX | 报告中心/对比平台/BI 大产品 |

### 2.2 系统六大目标（§🧭）

| 目标 | 状态 | Loop 动作 |
|------|------|-----------|
| 多源文档解析 | 🟡 | 维持 3 样本 L2；Stress 样本后置 |
| 结构化金融知识构建 | ✅ | 不回归 core_metric / grounding |
| 深度投研分析 | 🟡 | research graph + grounded synthesis（LLM 可用时） |
| 主动风险识别 | 🟡 | Risk LangGraph MVP（retrieve_risk→summarize）+ HAS_RISK；agent 经 orchestrator 路由 |
| 自动报告生成 | ❌ | **后置 P5** |
| 多公司对比分析 | ❌ | **后置 P5** |

### 2.3 已验证快照（2026-07-30）

| 项 | 值 |
|----|-----|
| §三 Knowledge 门禁 | ✅ 三样本 L3 全绿 |
| Phase A（P2） | ✅ 完成（fusion · OCF doc 级 · HAS_RISK 排序 · 工作台 fusion UI） |
| **Loop 主线** | **Phase B — P6 多智能体** |
| LangGraph 已注册 | `agent` · `orchestrator` · `quant` · `risk` |
| P6 已完成 | P6a–P6g · orchestrator · Decomposer-lite；P6h 后置 |
| Agent Chat 路由 | `orchestrator.classify_intent` → risk / quant / structured / research（`agent_chat/graph.py`） |
| L4 retrieval-only | ✅ 指南针 8/8（`l4_retrieval_pass_rate: 1.0`） |
| L4 完整 eval | ✅ **1.0**（8/8 znz）；证据 ID 清洗 · 合成降级 · 增长因果收紧 |
| Agent Chat 联调 | ✅ risk / quant / structured 路由绿；营收可 grounded 合成 |
| 已知阻塞 | 系统代理曾致 httpx→本地 LLM 502（已 `trust_env=False`）；Docker Desktop 偶发未开 |

**建议 pin**：`langgraph.env` → `AGENT_CHAT_DOC_ID=<最新 serving_eval doc_id>`

### 2.4 相对 Living Design 整体进度

| 维度 | 完成度 | 说明 |
|------|--------|------|
| 六层架构整体 | **~45%** | §四–§六 为主要增量 |
| Phase 1 主链 | **~80%** ✅ | 维持 P0 不回归 |
| §四 Reasoning 门禁 | **未开始** | Loop 目标：L4 + 多 Agent 图 |
| §五 Workflow 门禁 | **起步** | orchestrator · quant · risk 已注册；reporting 仍 stub |

---

## 3. 【A. 观测】— 每轮必做

### 3.1 健康检查（按序）

```powershell
# 1) LangGraph（必需）
Invoke-WebRequest http://127.0.0.1:2025/ok -UseBasicParsing -TimeoutSec 5

# 2) FastAPI（可选，工作台用）
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing -TimeoutSec 5

# 3) Docker（L3 实库需要）
docker ps --format "table {{.Names}}\t{{.Status}}"
# 期望：claude-copilot-postgres / qdrant / neo4j 为 Up
```

### 3.2 恢复动作（每轮每种服务最多重启 1 次）

```powershell
# LangGraph agent
$env:PYTHONUTF8='1'
cd D:\GithubProject\claude_copilot
.\scripts\run_agent_langgraph.ps1
# 默认 :2025，graph id: agent

# FastAPI（仅当本轮需要工作台/L3 看板 API）
cd D:\GithubProject\claude_copilot
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Agent Chat UI（仅当本轮验证前端）
cd D:\GithubProject\agent-chat-ui-main
pnpm install
pnpm dev
# :3000 · NEXT_PUBLIC_API_URL=http://localhost:2025
```

### 3.3 观测记录

**仅内部记录**（默认不写进用户消息）：`:2025` / `:8000` / docker / LLM / 本轮目标 Agent。

---

## 4. 【B. 真相 — 智能体与模块边界】

### 4.1 LangGraph 图

| 图 / 模块 | 路径 | 状态 | 说明 |
|-----------|------|------|------|
| `agent` | `app/workflows/agent_chat/graph.py` | ✅ | messages UI；`classify_intent` 路由 risk/quant/research |
| `orchestrator` | `app/workflows/orchestrator/graph.py` | ✅ MVP | `classify_intent` + 混合检索编排 · 已注册 langgraph.json |
| `quant` | `app/workflows/quant/graph.py` | ✅ MVP | YoY/CAGR · 已注册 langgraph.json |
| `risk` | `app/workflows/risk/graph.py` | ✅ MVP | retrieve_risk→summarize_risk · HAS_RISK · 已注册 langgraph.json |
| `research` | `app/workflows/research/graph.py` | ✅ | retrieve→synthesize→critique→revise（**未**注册 langgraph.json；agent 内联 ResearchService） |
| `reporting` | `app/workflows/reporting/` | ❌ stub | 仅 docstring |

### 4.2 Living Design §四 Agent — 诚实地图

| 设计 Agent | 实际替代 | 状态 |
|------------|----------|------|
| Router Agent | orchestrator `classify_intent` | 🟡 MVP |
| Task Decomposer | — | ❌ |
| Research Agent | research graph + GroundedResearchEngine | 🟡 |
| Risk Agent | `workflows/risk/` LangGraph MVP | 🟡 MVP |
| Quant Agent | `workflows/quant/` LangGraph MVP | 🟡 MVP |
| Comparator Agent | — | ❌ |
| Critic Agent | research graph critique 节点 | 🟡 |

**禁止**：在文档或代码注释中声称 risk/reporting/Comparator 已「完成」。

### 4.3 检索通道（§三）

| 通道 | 实现 | 配置 |
|------|------|------|
| Vector | Qdrant + `SiliconEmbeddingService` | `EMBEDDING_BACKEND=silicon`，collection `document_segments_bge_m3` |
| Lexical | BM25-lite `app/core/db/lexical.py` | 与 vector 加权融合 0.65/0.35 |
| Rerank | Silicon / deterministic | `RERANK_BACKEND` |
| SQL | Postgres `metric_facts` | Serving 闸门后入库 |
| Graph | Neo4j / local JSON · **2-hop** | `GRAPH_STORE_BACKEND`；`store.py` `_collect_paths` |
| Fusion | `FusionSummary` | orchestrator 三通道摘要 → API |
| SQL 回退 | doc 无指标 → company  scope | `orchestrator._retrieve_metrics` + warning |

---

## 5. 【C. 优先级队列】

### P0 — 保活 + 门禁（始终最高）

- LangGraph `:2025` 必须 OK。
- **改 pipeline / serving / 检索后**必跑其一：
  - 快：`.\.venv\Scripts\python.exe scripts/run_acceptance_suite.py --profile smoke`
  - 全：`.\.venv\Scripts\python.exe scripts/run_acceptance_suite.py --profile all`
- **不可回归**：
  - L2：`core_metric_exact_match == 1.0`，`source_grounding_rate >= 0.95`
  - L3：各样本 `l3_pass_rate == 1.0`

### P1 — Application §6.1 Agent Chat ✅ 已稳

**验收标准（Serving 指南针 doc）**
- 问：「2021年营业收入是多少？」
- 期望主答案：**931944638**
- 路由：`intent=structured`，`routes=['sql']`
- LLM 502 时：答案含结构化指标 + 中文说明（`_humanize_warning`）

**快验命令（仅 LangGraph 重启后或用户要求时）**

```powershell
# Python 探针 LangGraph（doc_id 用 configurable）
# 或浏览器 http://localhost:3000
```

**勿**每轮重复 P1 全量 E2E（浪费时间）。

### P2 — Knowledge §三 混合检索

#### 已完成的子项 ✅
- BM25-lite 词法（`app/core/db/lexical.py`）
- Query expansion（`app/core/rag/query_expansion.py`）
- Section hints + retriever boost（`QueryAnalyzer.section_hints`）
- `ResearchHit.metadata`（含 `section_type`）
- **fusion_summary**（`FusionSummary` → `ResearchPreviewResponse`）
- **Graph 2-hop**（`app/core/kg/store.py` · `tests/core/kg/test_graph_search.py`）
- **SQL 公司级回退**（doc 无指标时按 company 查，warning 标注）
- L3 指南针单样本 8/8 实库复验

#### 当前主线（**每轮只选一个**）

| 优先级 | 子项 | 目标 | 命令/文件 | 状态 |
|--------|------|------|-----------|------|
| **P2c** | **3 样本 L3 回归** | 指南针+聚灿+天华 L3 全绿 → **§三门禁** | `run_acceptance_suite.py --profile all` | ✅ |
| **P2d** | section 命中硬断言 | L3 semantic 题校验 `ResearchHit.metadata.section_type` | `run_serving_ingest_eval.py` | ✅ |
| P2e | fusion 进工作台 UI | `web/` 研究卡展示 fusion_summary | `web/src/App.tsx` | ✅ |
| **P2f** | OCF doc 级入库一致性 | 重复 ingest 时保证 OCF 写入当前 doc | `serving_facts.py` · `parsed_document_repository.py` | ✅ |

#### P2 改完必跑（按序）

```powershell
cd D:\GithubProject\claude_copilot
docker compose up -d postgres qdrant neo4j

# 1) 单测
.\.venv\Scripts\python.exe -m pytest tests/core/rag tests/core/kg -q

# 2) L3 指南针实库（改检索后）
.\.venv\Scripts\python.exe scripts/run_serving_ingest_eval.py `
  --storage-backend postgres --vector-backend qdrant --graph-backend neo4j

# 3) 三样本门禁（P2c 必跑）
.\.venv\Scripts\python.exe scripts/run_acceptance_suite.py --profile all
```

#### L3 题集摘要（指南针 8 题）

| id | 问句要点 | expect_route |
|----|----------|--------------|
| q_revenue_2021 | 2021 营业收入 | structured |
| q_revenue_2020 | 2020 营业收入 | structured |
| q_ocf_2021 | 2021 经营现金流 | structured |
| q_mda_overview | 管理层讨论 | semantic |
| q_revenue_growth_hybrid | 营收为何增长 | hybrid |
| q_market_risk_graph | 市场风险 | graph |
| q_industry_graph | 所在行业 | graph |
| q_reports_metric_graph | 指标关联 | graph |

### P3 — Document AI §二（小步）

- 仅当 P0/P2 均绿且改动触及 pipeline 时：`run_stage_eval.py --compare-baseline`
- **禁止**：§2.8 Document Fusion Engine 大建

### P4 — Reasoning §四 L4（多智能体质量闸门）

```powershell
# 完整 L4（需本地 LLM 非 502；评 grounded + critic + citations）：
.\.venv\Scripts\python.exe scripts/run_l4_research_eval.py

# 离线基线（LLM 502 时；评 evidence + 结构化数值 + fusion）：
.\.venv\Scripts\python.exe scripts/run_l4_research_eval.py --retrieval-only
```

- LLM 不可用 → 跑 **P4 离线** + 继续 **P6 图结构/Quant/Risk 节点**（不阻塞搭建）
- L4 完整达标 + critic 稳定 → 才宣称 §四「起步」

### P6 — 多智能体搭建与执行（**当前 Loop 主线**）

每 tick **只选一个**子项；完成后再 tick 下一项。LLM 502 时优先 **不依赖 LLM 的节点**（Quant、Router 增强、Risk 检索子图）。

| 优先级 | 子项 | 目标 | 路径/命令 | 验收 |
|--------|------|------|-----------|------|
| **P6a** | L4 离线基线 | Docker 下 `--retrieval-only` 指南针 8 题 | `run_l4_research_eval.py` | `l4_retrieval_pass_rate` |
| **P6b** | Research 图加固 | `fusion_summary` 经 graph state；critic 降级可测 | `workflows/research/` | pytest + preview |
| **P6c** | **Risk Agent MVP** | 独立 LangGraph：`retrieve_risk → summarize`（可先规则+检索） | `workflows/risk/` · `langgraph.json` | 图题 HAS_RISK + 风险问句 |
| **P6d** | Router / Decomposer -lite | 复杂问句拆子任务（规则或 LLM）；路由到 research/risk/quant | `QueryAnalyzer` 或新节点 | 混合/多意图用例 |
| **P6e** | Quant 子图显式化 | CAGR/YoY 作为 LangGraph 节点或 tool，供多 Agent 调用 | `orchestrator._calculate` | 增长题不 hallucinate |
| **P6f** | Agent Chat 多图路由 | `agent` 图按 intent 调 research/risk 子图 | `agent_chat/graph.py` | :3000 风险/营收问句 |
| P6g | L4 完整（LLM 恢复后） | grounded + critic 批量 | `run_l4_research_eval.py` | ✅ **1.0**（8/8 znz） |
| P6h | Comparator / reporting | **仅用户点名** | stub 目录 | — |

**多智能体搭建原则**
- 每个 Agent = **LangGraph 子图或节点** + **明确输入/输出 TypedDict** + **至少 1 个 pytest**。
- 先 **接线 ResearchService / Orchestrator**，再叠 LLM；502 时子图仍须返回证据。
- 新 graph 注册 `langgraph.json` 后，文档同步 `docs/agent_chat_ui.md`（若对用户可见）。

**改 P6 且触及共享检索时**：`pytest tests/core/rag tests/core/kg -q` → `--profile smoke`（不必每 tick `--profile all`）。

### P5 — 后置（Loop 默认不做）

- §6.2 自动报告 · §6.3 对比 · §6.4 BI
- §5 五条标准工作流（LangGraph 节点化）
- Risk Agent MVP（§4.4）— **仅用户点名**

---

## 6. 【D. 前端边界】

### 6.1 agent-chat-ui-main（:3000）

允许小步（ChatGPT 风、克制中文）：
- 空状态 / 加载态 / 错误可恢复
- placeholder / 示例问句
- 工具调用标签中文化

**禁止**
- 搬入 L3 评测看板
- 大改主题/布局
- 在本仓库 `claude_copilot/web/` 复制 Agent Chat

### 6.2 claude_copilot/web（:5173）

- 文档列表 · 研究卡 · 指标表 · **L3 评测看板**
- 数据：`GET /api/v1/eval/serving*`

---

## 7. 【E. 自主思考与反思】— 每 tick 必做（仅内部，不对用户输出）

每 tick 在行动前/后完成 **Think → Act → Verify → Reflect** 循环（不必写入 chat，除非 milestone/阻塞）：

### 7.1 行动前（Think）

1. **阶段定位**：Phase A 已完；本轮是否真在做 **P6 多 Agent**，还是误回 P2 抛光？
2. **Agent 选型**：Living §4 哪一格？选 **一个** 子项（P6a–P6h）。
3. **依赖检查**：LLM 是否必需？若 502，改做 P6c 规则层 / P6e Quant / P6a 离线 L4。
4. **边界**：是否越权做 Comparator/reporting/BI 全量？

### 7.2 行动后（Reflect）

1. **Living 映射**：动了哪个 Agent/图？Honest map 是否仍准确？
2. **指标风险**：L2/L3 会否回归？若改了 rag/kg/pipeline → smoke。
3. **多 Agent 完整性**：有无「假完成」（仅改 docstring）？有无测试/eval？
4. **下一 tick**：单一 P6 子项 ID；若 blocked，备选路径是什么？

**偏离纠正**：在做 P5 大产品 / 空 stub 冒充 / 每命令汇报用户 → 立即停止，回 P6 或 P0。

### 7.3 静默协议（强制）

| 情况 | 对用户 |
|------|--------|
| 正常 tick 推进 | **零输出**（继续下一 tick） |
| L2/L3 smoke 通过 | **零输出** |
| 单测/pytest 通过 | **零输出** |
| 里程碑（如 Risk 图首通、L4 首绿、新 graph 注册） | **一行** ✅ |
| 宕机 / L2·L3 失败 / 无法自恢复 | **一行** ❌ + 最小修复动作 |
| 用户主动问进度 | 可摘要，仍保持简短 |

**禁止**：每轮结束写 G 格式长文；每次 `pytest`/ingest 后向用户汇报；「本轮完成 P6x，下轮 P6y」式刷屏。

---

## 8. 【F. 动作规则 — 决策树（多智能体版）】

```text
:2025 不健康?
  YES → P0 重启 LangGraph（最多 1 次）→ 仍失败则 ❌ 一行通知用户，停
  NO  → 继续

Docker 需要但不可用?（L4 离线 / serving 实库）
  YES → 尝试 docker compose up 1 次 → 仍失败则改做不依赖 Docker 的 P6（纯 pytest/图代码）
  NO  → 继续

本轮改了 pipeline / rag / kg?
  YES → pytest tests/core/rag tests/core/kg → --profile smoke
  NO  → 继续

Phase A（P2）回归?
  仅当 smoke 失败或距上次 profile all 已改检索核心 → --profile all

选本轮 P6 子项（§7 Think）:
  LLM 502 → P6a 离线 L4 / P6c Risk 规则层 / P6e Quant 节点
  LLM OK  → P6g 完整 L4 / P6b critic 加固 / P6d Decomposer

tick 结束:
  默认 → 静默，立即下一 tick
  milestone/blocker → 一行对用户
  不 commit
```

### 环境分离（必遵守）

| 用途 | 配置来源 | 说明 |
|------|----------|------|
| Chat / 合成 / critic | `.env` + `langgraph.env` | 本地 `LLM_MODEL_API_TYPE=openai` |
| Embedding / Rerank | `.env` | `EMBEDDING_BACKEND=silicon` 可保留 |
| Agent 默认 doc | `langgraph.env` | `AGENT_CHAT_DOC_ID` 可选 |

**禁止**：未经用户同意把 `langgraph.env` Chat 改 Silicon。

---

## 9. 【G. 输出格式】— 内部模板（默认不对用户展示）

### 9.1 内部单行（Reflect 用，不发送）

```text
tick | P6x | Agent/图 | verify | next | blocked?
```

### 9.2 对用户：仅两类消息

**里程碑（一行）**

```text
✅ P6c Risk 图首通：langgraph risk · HAS_RISK 问句 eval 5/5
```

**阻塞（一行 + 可选一行修复）**

```text
❌ L3 回归失败：jucan q_ocf_2021 → 回滚 dedupe 改动
```

### 9.3 禁止对用户的输出

- 每 tick 进度汇报、命令 exit code 列表、长篇 A–G 展开
- 「已完成 pytest」「正在跑 ingest」类中间状态
- 除非用户 **明确问**「进度如何」

---

## 10. §层完成门禁（宣称「可用」前）

| Living 层 | 门禁条件 |
|-----------|----------|
| §一 Ingestion | 3 样本 L2 acceptance 全过 |
| §二 Document AI | `core_metric_exact_match=1.0` + serving_gate allow |
| §三 Knowledge | 全 ready 样本 L3 `pass_rate=1.0` |
| §四 Reasoning | L4 批量达标 + critic 稳定（待定义阈值） |
| §五 Workflow | 除 research 外 ≥1 条 LangGraph 生产流 |
| §六 Application | Agent Chat 稳定 + 一条产品 API（报告或对比） |

---

## 11. 禁止清单（违反即偏离）

1. 实现 `risk` / `reporting` 工作流全量（无用户点名）
2. 引入 Dify 作为编排层
3. 在 agent-chat-ui 做 L3 看板
4. hash 与 silicon embedding 写入同一 Qdrant collection
5. LLM 失败时返回无依据数字
6. 每轮多个无关主题并行改
7. 擅自 commit/push 或改密钥
8. 宣称 Comparator / Decomposer / Document Fusion 已 production-ready

---

## 12. 关键路径速查

| 用途 | 路径 |
|------|------|
| 混合检索核心 | `app/core/rag/orchestrator.py` |
| 向量+词法 | `app/core/rag/retriever.py` |
| 词法评分 | `app/core/db/lexical.py` |
| 图谱 2-hop | `app/core/kg/store.py` |
| Fusion schema | `src/claude_copilot/schemas/research.py` → `FusionSummary` |
| Agent 桥 | `app/workflows/agent_chat/graph.py` |
| Research 多 Agent 图 | `app/workflows/research/graph.py` |
| Risk stub → MVP | `app/workflows/risk/` |
| LangGraph 注册 | `langgraph.json` |
| L4 eval | `scripts/run_l4_research_eval.py` |
| L3 脚本 | `scripts/run_serving_ingest_eval.py` |
| 验收 | `scripts/run_acceptance_suite.py` |
| Golden 指南针 | `data/golden/znz_2021_stage_expectations.json` |
| L3 报告 | `data/reports/serving_eval/*_serving_eval.json` |
| Loop 本文 | `docs/loop_playbook.md` |

---

## 13. 默认 Backlog（多智能体推进序）

**Phase A — §三 Knowledge** ✅（P2 全完成；P0 维护 smoke）

**Phase B — §四/§五 多智能体（Loop 默认）**
1. P6a L4 `--retrieval-only` 基线（Docker）
2. P6c Risk Agent MVP → 注册 LangGraph
3. P6e Quant 节点/tool 显式化
4. P6d Router-Decomposer lite
5. P6f Agent Chat 多图路由
6. P6g 完整 L4（LLM 恢复）
7. P6b critic / fusion state 加固

**Phase C — 后置（用户点名）**
8. P6h Comparator · reporting · §6.2–6.4 BI
```

---

## §三 给人类操作者的说明

### 如何启动一次 Loop

1. 确保 Docker 与 LangGraph 可用（或交给代理 P0 重启）。
2. 复制 **§一 启动命令** 到 Cursor。
3. 若上下文窗口有限，另附 **§二 完整正文** 或告知代理「读取 `docs/loop_playbook.md` §二」。

### 何时打断 Loop

- 需要 commit/push 时明确指令。
- 要切换主线（如「本轮改 risk」）时点名。
- LLM 环境变更后说明。

### 文档维护

- 每完成 Loop 里程碑，更新本文 **§2.3 已验证快照**。
- 混合检索进展同步 `docs/pipeline_eval_status.md`。

---

## §四 修订记录

| 日期 | 变更 |
|------|------|
| 2026-07-30 | **多智能体版 Loop**：主线 P6 · §7 Think-Reflect · 强制静默（禁止每终端汇报） |
| 2026-07-29 | Phase A 完成：§三门禁 · P2e/f · Agent fusion · L4 `--retrieval-only` |
| 2026-07-29 | 完善版 playbook 首版 |
