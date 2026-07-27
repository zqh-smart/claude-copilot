# Pipeline Eval Status & Next Optimizations

样本：指南针 2021 年报（174 页，`table_pdf`）  
Baseline：`data/reports/eval/baseline_scorecard.json`  
跑分：`py -3.11 scripts/run_stage_eval.py --compare-baseline`

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
- 第二份年报泛化回归
- 外部财报字段伪 golden
- CER/TEDS 全量标注
