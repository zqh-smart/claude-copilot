# Document Pipeline Evaluation Metrics

本文件定义 **L1/L2 阶段**评估指标，以及如何判断一次改动是正向还是负向优化。  
完整分层（含入库闸门、检索 L3、研究 L4）见 [`evaluation_system.md`](./evaluation_system.md)。

## 原则

1. **先 eval，再改代码**：改动前跑 `scripts/run_stage_eval.py` 生成 baseline。
2. **同文档对比**：默认用固定样本（如指南针 2021）对比，避免样本漂移掩盖回归。
3. **指标有方向**：`higher_better` / `lower_better`，对比脚本自动标注 `+` / `-` / `=`。
4. **覆盖率 ≠ 准确率**：表多、段落多不一定更好；关键财务值要用 golden 精确校验。

## 常规文档解析 / DocAI 指标（行业常用）

| 类别 | 指标 | 含义 |
|------|------|------|
| 文本抽取 | CER / WER | 相对人工转录的字符/词错误率（越低越好） |
| 文本抽取 | Text coverage | 有文本页占比 |
| 版面 | Block type accuracy | heading/paragraph/table 分类准确率 |
| 表格检测 | Precision / Recall / F1 | 表格区域是否找对 |
| 表格结构 | TEDS / cell accuracy | 单元格结构与内容是否正确 |
| 信息抽取 | Exact Match / F1 | 字段级（指标名、期间、数值） |
| 章节 | Boundary IoU / type F1 | 章节边界与类型 |
| 端到端 | Provenance coverage | 事实是否带页码/表来源 |
| 工程 | Latency / pages·s⁻¹ | 吞吐 |

本仓库当前落地的是 **可自动计算的工程指标 + 少量 golden + 原文回查**；完整 CER/TEDS 需人工标注页，现阶段不做。

推荐组合（无需全量标注）：

1. **少量核心 golden**：营收/净利等精确值（`core_metric_exact_match`）
2. **原文回查**：抽取事实的数值能否在 PDF 文本/源表中定位（`source_grounding_rate`）
3. **可选外部财报字段**：巨潮/东方财富等同口径字段（尚未接入）

## 本仓库分阶段 Scorecard

### 1. Parse

| metric | 方向 | 说明 |
|--------|------|------|
| `text_coverage` | ↑ | 非空页占比 |
| `parse_confidence` | ↑ | 路由质量分 |
| `table_count` | context |  alone 不决定好坏，需配合准确率 |
| `heading_ratio` | ↓* | heading/总块；过高通常是噪声（*在中文年报场景） |
| `pages_per_second` | ↑ | 解析吞吐 |

### 2. Cleaning

| metric | 方向 | 说明 |
|--------|------|------|
| `blocks_removed_ratio` | ↑* | 清洗掉的噪声块比例（过高可能误删正文） |
| `header_footer_remaining` | ↓ | 清洗后残留 header/footer |
| `toc_like_remaining` | ↓ | 清洗后仍像目录的行 |
| `duplicate_block_ratio` | ↓ | 近重复块占比 |

### 3. Segmentation

| metric | 方向 | 说明 |
|--------|------|------|
| `semantic_section_count` | context | 数量适中；爆炸通常是误匹配 |
| `required_section_types_hit` | ↑ | 是否覆盖期望类型（MD&A/财报/审计等） |
| `false_anchor_rate_proxy` | ↓ | 标题过长/含“详见”等非标题特征占比 |

### 4. Table intelligence + Schema

| metric | 方向 | 说明 |
|--------|------|------|
| `statements_with_periods_ratio` | ↑ | 报表有期间 |
| `statements_with_metrics_ratio` | ↑ | 报表有指标 |
| `core_metric_exact_match` | ↑ | golden 关键指标数值命中率（营收/净利等） |
| `source_grounding_rate` | ↑ | 事实数值能在原文/源表中找到的比例（防幻觉） |
| `source_table_grounding_rate` | ↑ | 有 `source_table_id` 时，数值落在该表内的比例 |
| `implausible_period_ratio` | ↓ | 脏年份（如 1993）占比 |
| `provenance_metric_ratio` | ↑ | metric_fact 带来源表/页 |

### 5. Chunking

| metric | 方向 | 说明 |
|--------|------|------|
| `segment_count` | context | 过多常=碎片化 |
| `semantic_section_share` | ↑ | 章节感知 chunk 占比 |
| `avg_segment_chars` | ↑* | 过短通常质量差（*有上限） |
| `tiny_segment_ratio` | ↓ | <40 字符片段占比 |

## 如何跑

```bash
# 首次：生成 baseline
uv run python scripts/run_stage_eval.py --save-baseline

# 改代码后：与 baseline 对比
uv run python scripts/run_stage_eval.py --compare-baseline

# 指定 PDF / 期望文件
uv run python scripts/run_stage_eval.py \
  --pdf-path "..." \
  --expectations data/golden/znz_2021_stage_expectations.json \
  --compare-baseline
```

报告输出：

- `data/reports/eval/latest_scorecard.json`
- `data/reports/eval/baseline_scorecard.json`（`--save-baseline`）
- `data/reports/eval/diff_vs_baseline.json`（`--compare-baseline`）

## 判定规则（简版）

- **正向**：`core_metric_exact_match` 不降，且 `source_grounding_rate`↑ / 噪声指标↓
- **负向**：`core_metric_exact_match`↓，或 `source_grounding_rate`↓，或 `tiny_segment_ratio` / `false_anchor_rate_proxy` / `implausible_period_ratio` 明显上升
- **仅数量变化**：`table_count` / `segment_count` 单独涨跌不算成功，必须看准确率与噪声指标
- **原文回查边界**：能证明「没瞎编」，不能单独证明「没漏抽」；漏抽仍靠少量 golden / 外部字段
