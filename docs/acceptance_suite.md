# Acceptance Suite（验收套件）

把「能跑一遍」收成可重复验收：分层命令、样本分层、通过标准。  
评估分层定义见 `docs/evaluation_system.md`。

---

## 0. 工作台前端（推荐查看结果）

避免只盯长 JSON：本地起 API + Vite 控制台。

```bash
# 终端 1 — API（需 docker: postgres/qdrant/neo4j）
uvicorn app.main:app --reload --port 8000

# 终端 2 — UI
cd web
npm install
npm run dev
# 打开 http://localhost:5173
```

控制台能力：文档列表、研究问答（路由/指标/证据卡）、公司指标表、**L3 评测看板**（pass_rate + 逐题 PASS/FAIL）、上传 PDF。原始 JSON 折叠在「详情」。

> Agent 对话页不在本仓库：见工作区 sibling `agent-chat-ui-main`（`pnpm dev` → :3000）。  
> L3 看板在本仓库 `web/`「评测看板」Tab，数据来自 `GET /api/v1/eval/serving` 与 `/serving/{doc_id}`。

---

## 1. 样本分层

| 集合 | 样本 | Golden | 状态 |
|------|------|--------|------|
| **Smoke** | 指南针 2021（300803） | `data/golden/znz_2021_stage_expectations.json` | ✔ ready（L2/L3 硅基复验 8/8） |
| **Regression** | 聚灿光电 2021（300708） | `data/golden/jucan_2021_stage_expectations.json` | ✔ ready（L2 exact=1.0；L3 5/5） |
| **Regression** | 天华新能 2021（300390） | `data/golden/tianhua_2021_stage_expectations.json` | ✔ ready（L2 exact=1.0；L3 5/5） |
| **Stress** | 共同药业 2021 扫描版（300966） | `data/golden/gongtong_2021_pdf_stress.json` | ✔ ready（174 页无文本层；MinerU 真实 OCR 3 页） |
| **Table Stress** | 共同药业扫描版第 86 页资产负债表 | `data/golden/gongtong_2021_table_stress.json` | ✔ ready（47 行结构表；原 PDF 页码与 provenance） |
| **Conflict E2E** | 广州浪奇 2020 + 2021（000523） | `data/golden/guangzhou_langqi_conflict_e2e.json` | ✔ ready（真实追溯重述；PostgreSQL 胜者唯一） |

**门禁约定**：改 pipeline / serving / 检索后，先跑 Smoke，再跑 Regression；**全部 ready 样本都过**才可宣称 Knowledge Layer「检索可用」。

PDF 默认目录（本机）：

```text
Z:/BaiduNetdiskDownload/阶段12：LLM大型复杂项目实战/项目实战2：大模型金融对话交互系统/allpdf-part1/
```

| 样本 | 文件名 |
|------|--------|
| Smoke | `2022-01-25__北京指南针科技发展股份有限公司__300803__指南针__2021年__年度报告.pdf` |
| Regression | `2022-01-29__聚灿光电科技股份有限公司__300708__聚灿光电__2021年__年度报告.pdf` |
| Regression | `2022-02-08__苏州天华新能源科技股份有限公司__300390__天华新能__2021年__年度报告.pdf` |
| Stress | `2022-04-22__湖北共同药业股份有限公司__300966__共同药业__2021年__年度报告.pdf` |
| Conflict E2E | `…000523…2020年…年度报告.pdf` + `…000523…2021年…年度报告.pdf` |

---

## 2. 通过标准（单文档）

### L2 / Serving 闸门

自动化结果须同时满足（相对该文档 golden）：

- `core_metric_exact_match == 1.0`（golden 中有核心指标时）
- `source_grounding_rate >= 0.95`
- `implausible_period_ratio == 0`
- `statements_with_metrics_ratio == 1.0`
- `serving_gate.allow_metric_serving == true`
- 文档 `company` / `year` 非空

`run_stage_eval.py`：闸门不通过时 exit code `3`。

### L3 检索

- `run_serving_ingest_eval.py`：`l3.pass_rate == 1.0`（全部 `retrieval_cases` 通过）
- 生产复验：`EMBEDDING_BACKEND=silicon`、无 hash fallback、向量维 = `EMBEDDING_DIMENSIONS`、collection 与模型一致（当前 `document_segments_bge_m3` / 1024）
- Silicon 不可用时默认失败；仅离线调试加 `--allow-hash-fallback`

### L4（可选，非 L2/L3 硬门禁）

Grounded research + critic 批量题集。依赖 L3 已入库文档 + 可用 LLM（`LLM_MODEL_*` / Silicon chat）。

- 脚本：`scripts/run_l4_research_eval.py`
- 题集：golden 中 `l4_cases`（若有）否则 `retrieval_cases`
- 多样本：`--profile smoke|regression|all`（znz / 聚灿+天华 / 三者）
- 通过标准（单题 · full）：`grounded=true`、`critic.passed=true`、有证据时含 citations；有 `expect_value` 时数值出现在 answer/metrics
- 报告：`data/reports/l4_eval/*_l4_eval.json`；汇总 `latest_l4_summary.json`
- Exit code：`0` 全过；`2` 部分失败 / soft 未达标；`4` LLM 不可用（不阻塞 L2/L3）

**Pass 阈值（文档化 · P7e）**

| 模式 / 样本 | 阈值 | 含义 |
|-------------|------|------|
| `--retrieval-only`（任意样本） | `pass_rate == 1.0` | L4 证据基线；宣称 L4-ready 前必须绿 |
| Full · smoke（znz） | `pass_rate == 1.0` | **不回归**硬闸（LLM 可用时） |
| Full · regression（聚灿/天华） | `pass_rate >= 0.8` | 软闸：扩样目标，未进 acceptance 硬门禁 |

**尚未纳入 `run_acceptance_suite.py` 硬门禁**；LLM 502/不可用时跳过即可。

### PDF Stress

扫描件门禁使用真实 174 页、源文本覆盖率为 0 的年度报告，并通过生产 PDF router 调用 MinerU。为控制日常耗时，固定解析前 3 页；以下指标必须同时通过：

- route/backend 为 `mineru_pdf` / `mineru`，禁止静默回退
- 总页数 174、源文本覆盖率 0、解析页数 3
- 解析文本覆盖率不低于 0.66、恢复文本不少于 1000 字
- golden 中 6 个公司/报告/风险关键短语召回率为 1.0

---

## 3. 命令清单

前置：

```bash
docker compose up -d postgres qdrant neo4j
# .env：SILICON_KEY 有效；EMBEDDING_BACKEND=silicon
```

### 3.1 Smoke（每次改 pipeline / serving / 检索必跑）

```bash
# L1/L2 scorecard + serving_gate
python scripts/run_stage_eval.py --compare-baseline

# Serving 入库 + L3（硅基 embedding，禁止静默 hash）
python scripts/run_serving_ingest_eval.py \
  --storage-backend postgres \
  --vector-backend qdrant \
  --graph-backend neo4j
```

可选一键：

```bash
python scripts/run_acceptance_suite.py --profile smoke
```

默认流程现在依次执行：Serving Gate/冲突/负面 invariant 单测 → L1/L2 → Serving/L3 →
HTTP API smoke。仅在诊断外部 API 环境时使用 `--skip-api`；仅在单独调试样本时使用
`--skip-invariants`。

### 3.2 Regression（聚灿光电 + 天华新能，日常门禁第二关）

```bash
python scripts/run_acceptance_suite.py --profile regression
```

会依次跑 `REGRESSION_SAMPLES`（`jucan_2021`、`tianhua_2021`）的 L2 stage_eval + Serving/L3。

全套件一键（先 smoke 再 regression）：

```bash
python scripts/run_acceptance_suite.py --profile all
```

`all` 包含 Smoke、两个 Regression 和 Stress；也可只跑扫描件门禁：

```bash
python scripts/run_acceptance_suite.py --profile stress
python scripts/run_acceptance_suite.py --profile table-stress
python scripts/run_acceptance_suite.py --profile conflict
python scripts/run_acceptance_suite.py --profile soak
```

Conflict profile 顺序入库广州浪奇 2020/2021 两份真实年报，验证 `revenue::2020` 从旧文档值
`1541.76` 切换为 2021 年报追溯重述值 `1573944822.05`，同时要求 PostgreSQL 仅保留一个
grounded 胜者且新文档持久化明确 conflict warning。

### 3.3 L4（可选，LLM 可用时）

前置：Smoke/Regression L3 已跑通（Serving 轨有 `doc_id`）；本地或 Silicon chat 可响应。

```bash
# 默认指南针 golden + 自动解析 doc_id
python scripts/run_l4_research_eval.py

# 多样本（P7e）
python scripts/run_l4_research_eval.py --profile all --retrieval-only   # 证据基线 1.0
python scripts/run_l4_research_eval.py --profile smoke                  # znz full，阈值 1.0
python scripts/run_l4_research_eval.py --profile regression             # 聚灿+天华 full，软闸 ≥0.8

# 指定 doc_id 或子集（仅单样本）
python scripts/run_l4_research_eval.py --doc-id <uuid>
python scripts/run_l4_research_eval.py --case-ids q_revenue_2021 q_mda_overview
```

LLM 不可用时 exit `4`，并写入 `data/reports/l4_eval/llm_unavailable.json`；不阻断 L2/L3 验收。
汇总：`data/reports/l4_eval/latest_l4_summary.json`。

### 3.4 HTTP API smoke（Knowledge Layer 检索，可选）

前置：同 §3.1（`docker compose up -d` + 已完成 **Serving 入库**，或本脚本 `--ingest`）。

使用 FastAPI `TestClient`（无需单独起 `uvicorn`）：

```bash
# 推荐：先跑 serving 入库，再 API smoke（自动从 DB / 最新 serving 报告解析 doc_id）
python scripts/run_serving_ingest_eval.py \
  --storage-backend postgres \
  --vector-backend qdrant \
  --graph-backend neo4j

python scripts/run_api_smoke.py \
  --storage-backend postgres \
  --vector-backend qdrant \
  --graph-backend neo4j
```

已知 `doc_id` 时：

```bash
python scripts/run_api_smoke.py --doc-id <completed_doc_id>
```

验收套件一键（L1/L2 + Serving/L3 + API）：

```bash
python scripts/run_acceptance_suite.py --profile smoke --with-api
```

**断言（全部通过 exit 0）：**

| 检查 | 端点 | 期望 |
|------|------|------|
| 健康 | `GET /health` | `status == ok` |
| 公司列表 | `GET /api/v1/companies` | 含指南针 `company_id` |
| 结构化指标 | `GET /api/v1/companies/{id}/metrics?metric_key=revenue&year=2021` | `revenue` 2021 ≈ `931944638` |
| 检索路由 | `POST /api/v1/research/query`（golden `q_revenue_2021`） | 路由含 `sql`/structured；返回 metric 值匹配 |

未入库时脚本 exit `1` 并打印 prerequisite；断言失败 exit `2`。

### 3.5 单元测试（改代码后）

```bash
python -m pytest tests/test_serving_gate.py tests/test_serving_facts.py tests/test_stage_scorecard.py tests/core/rag tests/core/kg -q
```

---

## 4. 报告落点

| 产物 | 路径 |
|------|------|
| 最新 scorecard | `data/reports/eval/latest_scorecard.json` |
| baseline / diff | `data/reports/eval/baseline_scorecard.json`, `diff_vs_baseline.json` |
| Serving + L3 | `data/reports/serving_eval/*_serving_eval.json` |
| HTTP API smoke | stdout JSON（`scripts/run_api_smoke.py`） |
| L4 research + critic | `data/reports/l4_eval/*_l4_eval.json` |
| PDF Stress | `data/reports/eval/gongtong_2021_pdf_stress.json` |
| PDF Table Stress | `data/reports/eval/gongtong_2021_table_stress.json` |
| 跨文档冲突 E2E | `data/reports/eval/guangzhou_langqi_conflict_e2e.json` |
| Worker PostgreSQL soak | `data/reports/eval/ingestion_worker_soak.json` |
| 样本快照说明 | `docs/pipeline_eval_status.md` |

（`data/reports/*` 默认 gitignore；以本地报告 + 本套件文档为准。）

---

## 5. Regression golden 数值来源

### 聚灿光电（300708）

| 指标 | 2021 | 2020 |
|------|-----:|-----:|
| revenue（营业收入） | 1311334600.52 | 1279195406.04 |
| net_cash_from_operating_activities | 465398314.38 | 232760752.03 |

现金流行核对：`经营活动产生的现金流量净额 | 465,398,314.38 | 232,760,752.03 | 99.95`（末列同比%已丢弃）。  
相对期间 `current_period`/`prior_period` 在 schema 映射中按报告年度解析为 2021/2020。

### 天华新能（300390）

| 指标 | 2021 | 2020 |
|------|-----:|-----:|
| revenue（营业收入） | 469378042.95 | 565068173.71 |
| net_cash_from_operating_activities | 180482013.62 | 349953492.93 |

现金流行核对：`经营活动产生的现金流量净额 | 180,482,013.62 | 349,953,492.93 | -48.43`（末列同比%已丢弃）。

---

## 6. 最近复验（硅基）

| 样本 | L2 | L3 | 备注 |
|------|----|----|------|
| 指南针 Smoke | exact/grounding 达标 | 8/8 | collection `document_segments_bge_m3` |
| 聚灿 Regression | `core_metric_exact_match=1.0` | **5/5** | — |
| 天华新能 Regression | `core_metric_exact_match=1.0` | **5/5** | 报告 `c8fb1d29…_serving_eval.json` |
| 共同药业 Stress | 源文本覆盖率 0；恢复 1362 字 | 6/6 phrase | 3 页解析覆盖率 1.0；无回退 |
| 共同药业 Table Stress | 第 86 页；47 行 | 2/2 关键行 | 表头/页码/source block 全匹配；无回退 |
| 广州浪奇 Conflict | 2020/2021 双 PDF 完成入库 | winner 唯一 | 18 warnings；grounded winner 值正确 |

日期参考：2026-08-01。指南针默认 smoke 已复验：invariants 14/14、L2 gate 通过、
L3 8/8、HTTP API 4/4。

---

## 7. 明确未覆盖（避免误判「已整体测试」）

- L4 有独立脚本但未进 `run_acceptance_suite.py` 硬门禁（LLM 可用时可选跑）  
- 跨文档冲突已覆盖真实 PDF→pipeline→PostgreSQL E2E；尚未覆盖三份以上来源及公告/研报混合来源
- Stress 已覆盖真实扫描件 OCR 与复杂表结构；尚未覆盖低清、旋转、手写等更极端图像质量
