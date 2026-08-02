# Pipeline Eval Status & Next Optimizations

验收套件（命令 / 通过标准 / 样本分层）：`docs/acceptance_suite.md`

样本：指南针 2021 年报 — **Smoke**  
Regression：聚灿光电 2021 + 天华新能 2021（`jucan_*` / `tianhua_*` golden，均 ready）  
Baseline：`data/reports/eval/baseline_scorecard.json`  
跑分：`python scripts/run_stage_eval.py --compare-baseline`  
门禁：`python scripts/run_acceptance_suite.py --profile all`  
工作台：`cd web && npm run dev`（API：`uvicorn app.main:app --reload`）

## 当前指标（P7 / Phase F 后）

| metric | value | 备注 |
|--------|------:|------|
| core_metric_exact_match | **1.0** | 含修正后的经营现金流 2021/2020 |
| source_grounding_rate | **1.0** | |
| source_table_grounding_rate | ~0.99 | |
| required_section_types_hit | **1.0** | |
| implausible_period_ratio | **0.0** | |
| tiny_segment_ratio | **~0.01** | |
| statements_with_metrics_ratio | **1.0** | 空壳 statement 已剔除 |

### Golden（已校正）

- revenue 2021/2020 = 931944638 / 691620925
- net_cash_from_operating_activities 2021/2020 = **373048933 / 230581891**  
  （旧 golden 把 2020 值误标成 2021，源自同比%列错位）

## 已完成

- P0 脏期间 · P1 语义章节 · P2 源表绑定 · P3 chunk 碎片
- **P4** 无 metrics 的 statement 不再入库
- **P5** 同行大额金额存在时丢弃同比/百分比列；修正现金流黄金值
- **P6** statement 标题与类型不一致时回退到标准名（利润表/资产负债表/…）

## 可后置

- 重复块再降、旁支表章节噪声
- 扩充更多外部财报页面的 CER/TEDS 人工标注（当前 JPMorgan 2024 Form 10-K 第 5 页已落地并通过）

已完成：API smoke、负面 invariants、真实跨文档冲突 E2E、扫描 OCR Stress、复杂表 Stress、L4 grounded + critic 硬门禁、外部 JPM CER/TEDS 与真实 MinerU schema benchmark、
多进程 Worker soak 均已纳入 `--profile all`。

## 混合检索（近期）

- **BM25-lite 词法通道**：`app/core/db/lexical.py`（中英分词 + 长度归一），Local/Postgres segment repo 共用
- **Query expansion**：管理层/风险/营收/增长等双语扩展（`query_expansion.py`）
- **章节提示加权**：`QueryAnalyzer.section_hints` → retriever 对 `management_discussion` 等章节 +0.15 boost
- **证据元数据回传**：`ResearchHit.metadata` 含 `section_type`，L3 语义题可校验章节命中
- **fusion_summary**：Orchestrator 三通道可读摘要（`FusionSummary` → `ResearchPreviewResponse`）
- **Graph 2-hop**：风险/行业/事件二跳路径（`app/core/kg/store.py`）
- **SQL 公司级回退**：当前 doc 无指标时按 company 查（带 warning）
- **P2f doc 级指标入库**：重复 ingest 时 `prefer_document_id` + 同 doc 去重（`metrics_index` 优先 + 现金流量表）
- **Graph HAS_RISK 排序**：风险问句优先 `HAS_RISK` 于 `AFFECTED_BY`（修复 jucan L3 图题回归）
- **P2e 工作台 fusion UI**：`web/src/App.tsx` 研究卡展示混合检索摘要（routes / counts / highlights）
- 回归：`pytest tests/core/rag tests/core/kg -q`（19 passed）
