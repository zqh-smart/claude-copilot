# Pipeline Eval Status & Next Optimizations

样本：指南针 2021 年报（174 页，`table_pdf`）  
Baseline：`data/reports/eval/baseline_scorecard.json`  
跑分：`py -3.11 scripts/run_stage_eval.py --compare-baseline`

## 当前指标（P0–P3 后，已刷新 baseline）

### Summary

| metric | before | after | 目标 | 结果 |
|--------|-------:|------:|------|------|
| core_metric_exact_match | 1.0 | **1.0** | 不降 | ✔ |
| source_grounding_rate | 1.0 | **1.0** | 不降 | ✔ |
| source_table_grounding_rate | 0.197 | **0.987** | >0.6 | ✔ |
| required_section_types_hit | 0.333 | **1.0** | ≥0.67 | ✔ |
| implausible_period_ratio | 0.226 | **0.0** | <0.05 | ✔ |
| tiny_segment_ratio | 0.314 | **0.010** | <0.15 | ✔ |
| statements_with_metrics_ratio | 1.0 | 0.778 | — | 轻微回落（空壳 statement） |

### 分阶段快照

| stage | 关键量 |
|-------|--------|
| parse | confidence 0.95 · tables 245 · blocks 1899 |
| cleaning | 1899→1651 · header/footer 0 · toc 0 |
| segmentation | types 含 `company_overview` / `management_discussion` / `financial_statement` / `audit_report` |
| schema | 9 statements · 78 metric_facts · periods 干净 · table grounding 0.987 |
| chunking | 828 segs · section-aware 18.1% · avg 282 chars · tiny 1.0% |

### Golden 精确值

- revenue 2021 = 931944638 ✔
- revenue 2020 = 691620925 ✔
- net_cash_from_operating_activities 2021 = 230581891 ✔

## 已完成的优化

1. **P0 脏期间**：按报告年 ±5 过滤；合并 statement 时丢弃离谱年份；**不重排**列顺序以免错位
2. **P1 语义章节**：识别 TOC 页码前缀（`11第三节...`）；召回 MD&A / 公司简介；拒绝「治理层责任」等假锚点
3. **P2 源表绑定**：metric_fact 绑定到真正含该值的表；行标签优先于继承标题（利润表不再被标成资产负债表）
4. **P3 Chunk 碎片**：合并短 page_block、过滤 TOC/噪声，tiny ratio 降到 ~1%

## 下一步（可选）

- 清理无 metrics 的空壳 statement（抬回 `statements_with_metrics_ratio`）
- 现金流次要期间错值（如 `2020: 61.79`）对齐
- 外部财报字段伪 golden（巨潮/东财）
- 全量 CER/TEDS 仍暂缓

## 判定口诀

- 正向：核心值与原文回查不降 + 上表目标指标改进
- 负向：`core_metric_exact_match`↓ 或 `source_grounding_rate`↓
- 无效：只涨 `table_count` / `segment_count`
