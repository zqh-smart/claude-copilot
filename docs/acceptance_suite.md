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

### L4（尚未纳入套件）

Grounded research + critic 批量题集：待本地/云端 LLM 稳定后另开。

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

### 3.3 单元测试（改代码后）

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

- HTTP API 端到端（`/research/query` 等）未进套件  
- L4 grounded + critic 未进套件  
- 跨文档指标冲突策略未自动化（文档 §4.2）  
- 负面用例（故意脏期间应被闸门拦截）未建题  
- Stress 样本（扫描件）未建  
