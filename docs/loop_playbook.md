# Loop Playbook — 生产化 Backlog（Living Design 对照）

> 自主迭代代理的操作手册。复制 **§一 启动命令** 到 Cursor `/loop` 即可；细则在 **§二**。  
> 权威设计：`docs/Financial Document Intelligenc....md`  
> 进度/指标：`docs/pipeline_eval_status.md` · 验收：`docs/acceptance_suite.md` · 评估分层：`docs/evaluation_system.md`  
> Agent Chat 桥接：`docs/agent_chat_ui.md`

**当前阶段**：P7a–P7f 与 Phase F 工程化收尾已完成。Loop 主线切换为生产化 Backlog：
状态文档统一 → 前端 E2E → 正式多文档报告 → L4 硬门禁 → tracing 实连 → 文档融合 / KG / 评测 / Worker 运维。

---

## §一 启动命令

### 标准（推荐，60 分钟 · 生产化 Backlog · 静默连续）

```text
/loop 60m 你是 Claude Copilot 生产化迭代代理。目标：按 docs/loop_playbook.md §13 的未完成顺序推进，每 tick 只做一个可验证子项；完成前必须定义并通过对应单测、集成、E2E 或量化门禁。禁止每轮终端命令后汇报；仅服务无法恢复、回归失败或里程碑时同步。编排使用 LangGraph（非 Dify）；不改密钥、不 commit/push，除非用户明确要求。
```

### 精简版（上下文紧张时）

```text
/loop 60m 生产化 Backlog。Read docs/loop_playbook.md §二/§13。每轮一个子项并先定义验收；静默连续；仅宕机、回归失败或里程碑同步用户。
```

### 其它时长

| 时长 | 用途 | 附加约束 |
|------|------|----------|
| `/loop 30m` | 快验/保活 | P0 + 单测/单图冒烟；或 L4 `--retrieval-only` |
| `/loop 60m` | 日常迭代 | **每 tick 一个 Backlog 子项** |
| `/loop 4h` | 半天推进 | 可连续 2–3 个子项；每项通过对应测试后再切换 |
| `/loop 8h` | 夜间长跑 | 依赖顺序推进；保留 L2/L3/Acceptance 不回归 |

---

## §二 完整正文（复制给 Loop 代理）

```markdown
# Claude Copilot 未完成工作自主迭代代理 — 指令

## 0. 身份与铁律

你是 Claude Copilot 仓库的**生产化工程代理**。Phase 1、P6、P7a–P7f 与 Phase F 已过关；
主战场是 §13 的后续工作，不重做已绿能力。

**铁律**
1. 每 tick **A→G 全流程** + **§7 自主反思**；**一轮只做一个 Backlog 子项**（一个 PR 量级）。
2. **静默执行**：正常 tick **不向用户输出**；反思与 G 格式仅写在心里/内部，**禁止**「每跑完一条终端命令就汇报」。
3. **不 commit / 不 push**，除非用户明确说「帮我 commit/push」。
4. **不改** `.env` / `langgraph.env` 密钥；**不擅自**把 Chat LLM 切到 Silicon。
5. 编排层是 **LangGraph**，不是 Dify；用图节点化 Agent，不引入 Dify UI/编排。
6. 宣称某能力「完成」前：有图/有 API/有测试或可复现 eval；**禁止**空 stub 冒充 production-ready 或 §6 产品面完成。
7. LLM 502/超时：**保留结构化检索 + fusion + 中文 warning**；多 Agent 路径应能 **降级到 Quant/检索/comparator/reporting 规则子图**。
8. 动 pipeline/rag/kg 时仍守 P0：**L2/L3 不可回归**。
9. §6.2–6.4 MVP 已存在；修改时保留 Agent Chat 与内部工作台边界，并补对应 E2E。

---

## 1. 系统拓扑（必须知晓）

```text
浏览器 :3000  agent-chat-ui-main
    → LangGraph API :2025   graph_id=agent（默认可选 comparator/reporting）
        → app/workflows/agent_chat/graph.py
            → orchestrator.classify_intent → risk / quant / structured / research
            → 可配置调用 comparator / reporting
                → Postgres / Qdrant / Neo4j / 本地 LLM

浏览器 :5173  claude_copilot/web/   （内部工作台：文档 / L3 看板 / 研究卡）
    → FastAPI :8000
        → ResearchService + eval / Compare / Report / Dashboard API

Docker: postgres:5432 · qdrant:6333 · neo4j:7687/7474
```

**Python 命令（Windows）**：一律 `cd D:\GithubProject\claude_copilot` 后  
`.\.venv\Scripts\python.exe …`（勿用 base Anaconda）。

---

## 2. Living Design 六层 — 进度与边界

### 2.1 总览

| 层 | Living § | 进度 | Loop 允许 | Loop 禁止 |
|----|----------|------|-----------|-----------|
| 一 Data Ingestion | §一 | ~85% | Worker 默认部署与事件唤醒 | 整栈换 Docling/LlamaParse/Tika |
| 二 Document AI | §二 | ~85% | serving_gate；外部 golden/CER/TEDS | 无基线的大范围 parser 重写 |
| 三 Knowledge Layer | §三 | **~85%** | 混合检索、GraphRAG MVP、fusion、2-hop | hash/real 混同一 Qdrant collection |
| 四 Reasoning | §四 | **~65%** | L4/critic 多样本硬门禁 | 无真实 eval 宣称 production-complete |
| 五 Workflow | §五 | **~70%** | 正式多文档报告与知识融合 | 引入 Dify 或复制现有图 |
| 六 Application | §六 | ~70% | 两套前端 E2E、可用性与错误态 | 在 `web/` 复制 Agent Chat |

### 2.2 系统六大目标（§🧭）

| 目标 | 状态 | Loop 动作 |
|------|------|-----------|
| 多源文档解析 | ✅ | 三样本 L2 + 扫描 OCR/复杂表 Stress；多文档知识融合仍单列后续 |
| 结构化金融知识构建 | ✅ | 不回归 core_metric / grounding |
| 深度投研分析 | 🟡 | 多 Agent 已接线；Full L4/critic 多样本尚未成为硬门禁 |
| 主动风险识别 | 🟡 | Risk 图与雷达/热力图可用；KG 关系质量仍需生产化 |
| 自动报告生成 | 🟡 | 公司/年度/类型 + HTML/PDF 可用；正文仍是提纲组合，待正式综合 |
| 多公司对比分析 | ✅ MVP | 跨文档矩阵、财务排名、风险雷达、业务重叠已上线；待浏览器 E2E |

### 2.3 已验证快照（2026-08-01）

| 项 | 值 |
|----|-----|
| §三 Knowledge 门禁 | ✅ 三样本 L3 全绿 |
| Phase A–B + P6h lite | ✅ 完成 |
| **Loop 主线** | 生产化 Backlog：状态统一 → E2E → 正式报告 → L4/tracing → fusion/KG/eval/Worker |
| LangGraph 已注册 | `agent` · `orchestrator` · `quant` · `risk` · `comparator` · `reporting` · `comparison_workflow` · `report_workflow` |
| L4 完整 eval | ✅ **1.0**（8/8 znz）；`--profile` 扩聚灿/天华；阈值已文档化 |
| P7 | P7a–P7f ✅ |
| Agent Chat 路由 | risk / compare / quant / structured / report / research |
| 本地代码基线 | ✅ `pytest -q` 215 passed / 1 skipped；Acceptance all exit 0；`web` build 通过 |
| 已知阻塞 | Docker Desktop 偶发未开；系统代理曾致 LLM 502（已 `trust_env=False`） |

**建议 pin**：`langgraph.env` → `AGENT_CHAT_DOC_ID=<最新 serving_eval doc_id>`；对比调试另备 `AGENT_CHAT_DOC_ID_B` 或 configurable。

### 2.4 相对 Living Design 整体进度

| 维度 | 完成度 | 说明 |
|------|--------|------|
| 六层架构整体 | **~75%** | 主链与 MVP 产品面可用；生产化 Backlog 见 §13 |
| Phase 1 主链 | **~90%** ✅ | Acceptance all 全绿；维持 core metric/grounding 不回归 |
| §四 Reasoning 门禁 | **可用 · 待硬化** | 多 Agent + critic 可跑；Full L4 多样本仍是软门禁 |
| §五 Workflow 门禁 | **可用 · 待深化** | 8 个图已注册；正式多文档报告/融合未完成 |
| §六 Application | ~70% | Agent Chat + 工作台 7 页可用；浏览器 E2E 未建立 |

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
| `reporting` | `app/workflows/reporting/graph.py` | ✅ lite | 提纲报告 · 已注册；无导出/报告中心 |
| `comparator` | `app/workflows/comparator/graph.py` | ✅ lite | 双 doc 指标矩阵 · 已注册；无对比平台 UI |

### 4.2 Living Design §四 Agent — 诚实地图

| 设计 Agent | 实际替代 | 状态 |
|------------|----------|------|
| Router Agent | orchestrator `classify_intent` + `decompose_question` lite | 🟡 MVP |
| Task Decomposer | `decompose_question` 规则拆句（非 LLM） | 🟡 lite |
| Research Agent | research graph + GroundedResearchEngine | 🟡 |
| Risk Agent | `workflows/risk/` LangGraph MVP | 🟡 MVP |
| Quant Agent | `workflows/quant/` LangGraph MVP | 🟡 MVP |
| Comparator Agent | `workflows/comparator/` LangGraph lite | 🟡 lite（无 UI） |
| Critic Agent | research graph critique 节点 | 🟡 |

**禁止**：宣称 reporting/Comparator/BI **产品面**已完成；lite 图 ≠ §6.2–6.4。

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
# 完整 L4 smoke（需本地 LLM 非 502；评 grounded + critic + citations）：
.\.venv\Scripts\python.exe scripts/run_l4_research_eval.py --profile smoke

# 多样本证据基线 / 聚灿+天华 full（软闸 ≥0.8）：
.\.venv\Scripts\python.exe scripts/run_l4_research_eval.py --profile all --retrieval-only
.\.venv\Scripts\python.exe scripts/run_l4_research_eval.py --profile regression
```

- LLM 不可用 → 跑 `--retrieval-only`；不阻塞 L2/L3
- L4 阈值：smoke full=1.0；retrieval-only=1.0；regression full≥0.8（见 acceptance_suite）

### P6 — 多智能体搭建（**已完成 · 勿回头大改**）

| 子项 | 状态 |
|------|------|
| P6a–P6g | ✅ L4 8/8 · Risk/Quant/Router/Agent 路由 |
| P6h lite | ✅ `comparator` · `reporting` 已注册（无 §6 UI） |

### P7 — 未完成加深（**P7a–P7f 已完成**）

每 tick **只选一个**子项。优先可验证、小 diff；默认**不做** §6.2–6.4 完整产品面。

| 优先级 | 子项 | 目标 | 路径/命令 | 验收 |
|--------|------|------|-----------|------|
| **P7a** | Agent/Orchestrator 接线 | 对比/报告意图可调 `comparator`/`reporting`；`doc_id_b` 经 configurable/env | `agent_chat/` · `orchestrator/` | ✅ intent 路由 + pytest |
| **P7b** | §5.4/5.5 工作流 lite | 串联 retrieve→compare 或 gather→outline→（可选）聚合；非 PDF 流水线 | `comparison_workflow` · `report_workflow` | ✅ 已注册 + pytest |
| **P7c** | 薄 Compare/Report API | `POST` 返回 JSON/Markdown 提纲或矩阵；**无**报告中心 UI、无强制 PDF | `app/api/v1/workflows.py` | ✅ `/api/v1/compare` · `/api/v1/report/outline` |
| **P7d** | 多 Agent 生产化 | Decomposer 增强、critic 稳、默认对话多意图；禁止假完成 | orchestrator / research / grounded | ✅ secondary + critic soft-fail + pytest |
| **P7e** | L4/验收加深 | 聚灿/天华 L4 或文档化 pass 阈值；维持 smoke | `run_l4_research_eval.py` | ✅ `--profile` + 阈值文档 + summary |
| **P7f** | §6.2–6.4 产品面 | 报告中心 / 对比看板 / BI | `web/` + `/api/v1/dashboard/portfolio` | ✅ 多年度 HTML/PDF + 多公司对比 + BI |

**P7 原则**
- 薄 API ≠ 报告中心；Markdown/JSON 输出即可。
- `comparator` 需要 **两个 doc**；缺 `doc_id_b` 时明确 warning，勿幻觉第二家公司。
- 改共享检索仍：`pytest tests/core/rag tests/core/kg -q` → 必要时 `--profile smoke`。

### P5 / §六大产品 — P7f MVP 已完成

- §6.2 自动报告中心：公司/年度范围/报告类型，Markdown/HTML/PDF 下载。
- §6.3 对比平台：跨文档矩阵、多公司财务排名、风险雷达、业务重叠度。
- §6.4 BI：指标趋势、行业分布、风险热力图、公司排名。

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

1. **阶段定位**：P7/Phase F 已完；本轮对应 §13 Phase G 哪一个子项？
2. **选型**：是否只选择一个可独立验收的小交付？
3. **依赖检查**：需要 Docker、浏览器、真实 LLM 或 tracing 凭据吗？缺失时能否先做离线契约？
4. **边界**：是否保持 Agent Chat 与内部工作台职责分离？

### 7.2 行动后（Reflect）

1. **Living 映射**：推进 Phase G 哪一项？Honest map / §2.3 是否需更新？
2. **指标风险**：L2/L3 会否回归？若改了 rag/kg/pipeline → smoke。
3. **完整性**：有无「假完成」（仅改 docstring）？有无测试/契约？
4. **下一 tick**：单一 Phase G 子项；若 blocked，备选路径是什么？

**偏离纠正**：空 stub 冒充 / 每命令汇报用户 / 重做已绿 P6/P7 / 同轮扩多个主题 → 立即停止，回 §13 当前子项或 P0。

### 7.3 静默协议（强制）

| 情况 | 对用户 |
|------|--------|
| 正常 tick 推进 | **零输出**（继续下一 tick） |
| L2/L3 smoke 通过 | **零输出** |
| 单测/pytest 通过 | **零输出** |
| 里程碑（如 Risk 图首通、L4 首绿、新 graph 注册） | **一行** ✅ |
| 宕机 / L2·L3 失败 / 无法自恢复 | **一行** ❌ + 最小修复动作 |
| 用户主动问进度 | 可摘要，仍保持简短 |

**禁止**：每轮结束写 G 格式长文；每次 `pytest`/ingest 后向用户汇报；「本轮完成 P7x，下轮 P7y」式刷屏。

---

## 8. 【F. 动作规则 — 决策树（Phase G 生产化版）】

```text
:2025 不健康?
  YES → P0 重启 LangGraph（最多 1 次）→ 仍失败则 ❌ 一行通知用户，停
  NO  → 继续

Docker 需要但不可用?（L4 / serving 实库）
  YES → 尝试 docker compose up 1 次 → 仍失败则改做不依赖 Docker 的契约/单测
  NO  → 继续

本轮改了 pipeline / rag / kg?
  YES → pytest tests/core/rag tests/core/kg → --profile smoke
  NO  → 继续

选本轮 Phase G 子项（§7 Think）:
  状态描述冲突 → 先统一 docs / AGENTS / skills
  UI E2E → 分别验证 :5173 工作台与 :3000 Agent Chat，不混边界
  正式报告 / L4 / tracing → 先确认真实外部依赖，再定义降级路径
  fusion / KG / eval / Worker → 保持现有协议可交换和 Acceptance 不回归

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
| Agent 默认 doc | `langgraph.env` | `AGENT_CHAT_DOC_ID`；对比可加 `AGENT_CHAT_DOC_ID_B` |

**禁止**：未经用户同意把 `langgraph.env` Chat 改 Silicon。

---

## 9. 【G. 输出格式】— 内部模板（默认不对用户展示）

### 9.1 内部单行（Reflect 用，不发送）

```text
tick | P7x | 主题 | verify | next | blocked?
```

### 9.2 对用户：仅两类消息

**里程碑（一行）**

```text
✅ P7c Compare API 首通：POST /api/v1/compare → matrix JSON
```

**阻塞（一行 + 可选一行修复）**

```text
❌ L3 回归失败：jucan q_ocf_2021 → 回滚 dedupe 改动
```

### 9.3 禁止对用户的输出

- 每 tick 进度汇报、命令 exit code 列表、长篇 A–G 展开
- 「已完成 pytest」「正在跑 ingest」类中间状态
- 「本轮完成 P7x，下轮 P7y」式刷屏
- 除非用户 **明确问**「进度如何」

---

## 10. §层完成门禁（宣称「可用」前）

| Living 层 | 门禁条件 |
|-----------|----------|
| §一 Ingestion | 3 样本 L2 acceptance 全过 |
| §二 Document AI | `core_metric_exact_match=1.0` + serving_gate allow |
| §三 Knowledge | 全 ready 样本 L3 `pass_rate=1.0` |
| §四 Reasoning | L4 retrieval 1.0；宣称 production 前需 Full L4/critic 多样本硬门禁 |
| §五 Workflow | 8 个 LangGraph 图已注册；正式报告需跨文档综合而非提纲拼接 |
| §六 Application | Agent Chat + 工作台生产构建通过；完成需两套前端浏览器 E2E |

---

## 11. 禁止清单（违反即偏离）

1. 无测试地大改已上线的 §6.2–6.4 产品面
2. 引入 Dify 作为编排层
3. 在 agent-chat-ui 做 L3 看板
4. hash 与 silicon embedding 写入同一 Qdrant collection
5. LLM 失败时返回无依据数字
6. 每轮多个无关主题并行改
7. 擅自 commit/push 或改密钥
8. 把提纲拼接称为正式报告，或把文档对比称为 Document Fusion
9. 回头大改已绿的 P6a–P6h（除非回归修复）

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
| Risk workflow | `app/workflows/risk/` |
| LangGraph 注册 | `langgraph.json` |
| L4 eval | `scripts/run_l4_research_eval.py` |
| L3 脚本 | `scripts/run_serving_ingest_eval.py` |
| 验收 | `scripts/run_acceptance_suite.py` |
| Golden 指南针 | `data/golden/znz_2021_stage_expectations.json` |
| L3 报告 | `data/reports/serving_eval/*_serving_eval.json` |
| Loop 本文 | `docs/loop_playbook.md` |

---

## 13. 默认 Backlog（未完成推进序）

**Phase A — §三 Knowledge** ✅
**Phase B — P6 多智能体** ✅（含 P6h lite 图注册）

**Phase D — 未完成加深（Loop 默认 = P7）**
1. ~~P7a Agent/Orchestrator 接线~~ ✅
2. ~~P7b §5.4/5.5 工作流 lite~~ ✅
3. ~~P7c 薄 Compare/Report API~~ ✅
4. ~~P7d 多 Agent 生产化（Decomposer/critic/多意图）~~ ✅
5. ~~P7e L4 扩样或阈值文档化~~ ✅

**Phase E — 产品面（仅用户点名 = P7f）**
6. ~~§6.2 报告中心 · §6.3 对比平台 · §6.4 BI~~ ✅

**Phase F — 工程化收尾** ✅
7. ~~P7/异步入库当前工作区恢复可重复测试基线~~ ✅ `172 passed` + web build
8. ~~异步任务领取/租约/心跳/fencing/独立 Worker/协作取消/指标/多进程 soak~~ ✅ `3×8` 任务、6 Worker、24/24 exactly-once
9. Acceptance 默认 API smoke + 冲突/负面 invariants ✅；真实跨文档冲突 E2E ✅；L4 保持独立可选门禁
10. ~~增加扫描件与复杂表 Stress golden~~ ✅ OCR 3 页（1362 字、6/6 phrase）+ 第 86 页 47 行表（页码/provenance/关键行全绿）
11. ~~队列监控告警契约~~ ✅ health + 4 类阈值 alerts + 工作台展示
12. ~~LangSmith / Langfuse tracing 集成（不只环境变量占位）~~ ✅ 统一 span + 默认脱敏 + exporter adapters
13. ~~对齐并维护项目进度文档~~ ✅

**Phase G — 当前生产化 Backlog**
14. 统一 docs / AGENTS / skills 状态真相源
15. `web/` 与 `agent-chat-ui-main/` 浏览器 E2E 门禁
16. 正式多文档投研/风控报告（综合正文，不是提纲拼接）
17. Full L4/critic 多样本硬门禁
18. LangSmith/Langfuse 真实 exporter 冒烟
19. 多文档 FinancialSchema / 知识融合
20. KG 实体消歧与关系质量生产化
21. 外部 golden、CER/TEDS 与重复块/旁支表噪声优化
22. 独立 Worker 默认部署、事件驱动唤醒与运维验收
```

---

## §三 给人类操作者的说明

### 如何启动一次 Loop

1. 确保 Docker 与 LangGraph 可用（或交给代理 P0 重启）。
2. 复制 **§一 启动命令** 到 Cursor（主线是 **Phase G 生产化 Backlog**）。
3. 一轮只选 §13 的一个子项，并在修改前写明验收指标。
4. 上下文有限时附 **§二** 或告知「读取 `docs/loop_playbook.md` §二」。

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
| 2026-08-01 | **P7f 完成**：多年度/类型报告包 HTML/PDF、跨文档与多公司对比、风险雷达/业务重叠、BI 趋势/行业/热力图/排名；tracing 与工程化收尾同步完成 |
| 2026-07-31 | **P7a–P7e 完成**：多意图生产化 + L4 `--profile`/阈值文档；余 P7f（§6 UI）点名 |
| 2026-07-31 | **Loop 主线切 P7 未完成加深**：启动命令/决策树/Backlog 对准接线·工作流 lite·薄 API；§6 UI 仍点名 |
| 2026-07-31 | P6h lite：Comparator + Reporting LangGraph 注册；§6.2–6.4 产品面仍后置 |
| 2026-07-31 | §四/§五 门禁标「起步」（L4 8/8 + multi-agent）；P6h/§六 报告·对比·BI 明确后置 |
| 2026-07-30 | **多智能体版 Loop**：主线 P6 · §7 Think-Reflect · 强制静默（禁止每终端汇报） |
| 2026-07-29 | Phase A 完成：§三门禁 · P2e/f · Agent fusion · L4 `--retrieval-only` |
| 2026-07-29 | 完善版 playbook 首版 |
