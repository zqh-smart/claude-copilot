# Acceptance Suite（验收套件）

把「能跑一遍」收成可重复验收：分层命令、样本分层、通过标准。  
评估分层定义见 `docs/evaluation_system.md`。

---

## 1. 样本分层

| 集合 | 样本 | Golden | 状态 |
|------|------|--------|------|
| **Smoke** | 指南针 2021（300803） | `data/golden/znz_2021_stage_expectations.json` | ✔ ready（L2/L3 硅基复验 8/8） |
| **Regression** | 聚灿光电 2021（300708） | `data/golden/jucan_2021_stage_expectations.json` | ✔ ready（L2 exact=1.0；L3 5/5） |
| Stress | 扫描件 / 复杂表 | 后置 | — |

**门禁约定**：改 pipeline / serving / 检索后，先跑 Smoke，再跑 Regression；**两份都过**才可宣称 Knowledge Layer「检索可用」。

PDF 默认目录（本机）：

```text
Z:/BaiduNetdiskDownload/阶段12：LLM大型复杂项目实战/项目实战2：大模型金融对话交互系统/allpdf-part1/
```

| 样本 | 文件名 |
|------|--------|
| Smoke | `2022-01-25__北京指南针科技发展股份有限公司__300803__指南针__2021年__年度报告.pdf` |
| Regression | `2022-01-29__聚灿光电科技股份有限公司__300708__聚灿光电__2021年__年度报告.pdf` |

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

### L4（可选，非硬门禁）

Grounded research + critic 批量题集。依赖 L3 已入库文档 + 可用 LLM（`LLM_MODEL_*` / Silicon chat）。

- 脚本：`scripts/run_l4_research_eval.py`
- 题集：golden 中 `l4_cases`（若有）否则 `retrieval_cases`
- 通过标准（单题）：`grounded=true`、`critic.passed=true`、有证据时含 citations；有 `expect_value` 时数值出现在 answer/metrics
- 报告：`data/reports/l4_eval/*_l4_eval.json`
- Exit code：`0` 全过；`2` 部分失败；`4` LLM 不可用（不阻塞 L2/L3 Knowledge Layer 工作）

**尚未纳入 `run_acceptance_suite.py` 硬门禁**；LLM 502/不可用时跳过即可。

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

### 3.2 Regression（聚灿光电，日常门禁第二关）

```bash
python scripts/run_acceptance_suite.py --profile regression
```

等价手写：

```bash
PDF="Z:/BaiduNetdiskDownload/阶段12：LLM大型复杂项目实战/项目实战2：大模型金融对话交互系统/allpdf-part1/2022-01-29__聚灿光电科技股份有限公司__300708__聚灿光电__2021年__年度报告.pdf"
GOLDEN=data/golden/jucan_2021_stage_expectations.json

python scripts/run_stage_eval.py \
  --pdf-path "$PDF" \
  --expectations "$GOLDEN" \
  --output data/reports/eval/jucan_2021_scorecard.json

python scripts/run_serving_ingest_eval.py \
  --pdf-path "$PDF" \
  --expectations "$GOLDEN" \
  --storage-backend postgres \
  --vector-backend qdrant \
  --graph-backend neo4j
```

双样本一键：

```bash
python scripts/run_acceptance_suite.py --profile all
```

### 3.3 L4（可选，LLM 可用时）

前置：Smoke/Regression L3 已跑通（Serving 轨有 `doc_id`）；本地或 Silicon chat 可响应。

```bash
# 默认指南针 golden + 自动解析 doc_id
python scripts/run_l4_research_eval.py

# 指定 doc_id 或子集
python scripts/run_l4_research_eval.py --doc-id <uuid>
python scripts/run_l4_research_eval.py --case-ids q_revenue_2021 q_mda_overview
```

LLM 不可用时 exit `4`，并写入 `data/reports/l4_eval/llm_unavailable.json`；不阻断 L2/L3 验收。

LLM 不可用时 exit `4`，并写入 `data/reports/l4_eval/llm_unavailable.json`；不阻断 L2/L3 验收。

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
| 样本快照说明 | `docs/pipeline_eval_status.md` |

（`data/reports/*` 默认 gitignore；以本地报告 + 本套件文档为准。）

---

## 5. 聚灿光电 golden 数值来源

| 指标 | 2021 | 2020 |
|------|-----:|-----:|
| revenue（营业收入） | 1311334600.52 | 1279195406.04 |
| net_cash_from_operating_activities | 465398314.38 | 232760752.03 |

现金流行核对：`经营活动产生的现金流量净额 | 465,398,314.38 | 232,760,752.03 | 99.95`（末列同比%已丢弃）。  
相对期间 `current_period`/`prior_period` 在 schema 映射中按报告年度解析为 2021/2020。

---

## 6. 最近复验（硅基）

| 样本 | L2 | L3 | 备注 |
|------|----|----|------|
| 指南针 Smoke | exact/grounding 达标 | 8/8 | collection `document_segments_bge_m3` |
| 聚灿 Regression | `core_metric_exact_match=1.0` | **5/5** | 报告 `c58087fa…_serving_eval.json` |

日期参考：2026-07-27。

---

## 7. 明确未覆盖（避免误判「已整体测试」）

- HTTP API smoke 未进默认 `--profile smoke`（需 `--with-api` 或单独跑 `run_api_smoke.py`）  
- L4 有独立脚本但未进 `run_acceptance_suite.py` 硬门禁（LLM 可用时可选跑）  
- 跨文档指标冲突：已实现 grounded+provenance 优胜 + warning（单测覆盖；未进 acceptance 脚本硬门禁）  
- 负面用例（故意脏期间应被闸门拦截）未建题  
- Stress 样本（扫描件）未建  
