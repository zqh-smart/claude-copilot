# Pipeline Eval Status & Next Optimizations

验收套件（命令 / 通过标准 / 样本分层）：`docs/acceptance_suite.md`

样本：指南针 2021 年报（174 页，`table_pdf`）— **Smoke**  
Regression：聚灿光电 2021（`data/golden/jucan_2021_stage_expectations.json`，ready；L3 5/5）  
Baseline：`data/reports/eval/baseline_scorecard.json`  
跑分：`python scripts/run_stage_eval.py --compare-baseline`  
门禁：`python scripts/run_acceptance_suite.py --profile all`（先 smoke 再 regression）

## 当前指标（P4–P6 后）

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
- 跨文档同指标冲突策略（`evaluation_system.md` §4.2）
- API 层 smoke（`/research/query`）进验收套件
- L4 grounded + critic（LLM 稳定后）
- 外部财报字段伪 golden / CER/TEDS 全量标注
