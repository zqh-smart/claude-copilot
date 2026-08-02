# Evaluation System（入库前先定评什么）

本文定义 Claude Copilot 的**分层评估体系**：先能判定「解析/结构/检索/回答」好坏，再谈往 Postgres / Qdrant / Neo4j 灌数据。  
原则：**库里存的是评估已放行的事实与片段，而不是解析器的全部中间噪声。**

---

## 1. 为什么先评估、后入库

| 存储 | 写入内容 | 评估没过时的风险 |
|------|----------|------------------|
| Postgres | `metric_facts` / company metrics | 错金额、错期间变成「权威 SQL 事实」 |
| Qdrant | segments 向量 | 脏 chunk 污染语义检索 |
| Neo4j | Company–Metric–Period 边 | 错边在图谱里被反复引用 |

因此评估不是解析附属品，而是**入库闸门（gate）**。

---

## 2. 五层评估模型

```text
L0 工程可跑     管道不崩、有耗时、有路由
L1 文档解析     文本/表/章节/清洗（当前 stage scorecard 主体）
L2 金融结构     核心指标 golden + 原文回查 + 溯源（入库硬闸门）
L3 检索可用     SQL / 向量 / 图谱 能否答对固定问题（入库后立刻验）
L4 研究闭环     Grounded Research + Critic 是否引用正确证据（产品层）
```

### L0 — 工程可跑

| 指标 | 含义 | 现状 |
|------|------|------|
| pipeline success | 全阶段无异常完成 | 脚本可跑 |
| stage latency | parse/clean/… 耗时 | scorecard `timings` |
| parse_route / confidence | 路由是否合理 | 已有 |

**用途**：CI smoke；不证明财务正确。

### L1 — 文档解析质量

对应 `docs/eval_metrics.md` 中 parse / cleaning / segmentation / chunking。

| 关注点 | 代表指标 | 方向 |
|--------|----------|------|
| 文本可得性 | `text_coverage` | ↑ |
| 噪声 | `heading_ratio`, `toc_like_remaining`, `tiny_segment_ratio` | ↓ |
| 章节召回 | `required_section_types_hit`, `false_anchor_rate_proxy` | ↑ / ↓ |
| 吞吐 | `pages_per_second` | ↑（次要） |

**不做**：全页 CER/TEDS（成本过高，现阶段收益低）。

### L2 — 金融结构正确性（入库硬闸门）

| 指标 | 含义 | 闸门 |
|------|------|------|
| `core_metric_exact_match` | 少量核心字段与 golden 一致 | **必须 = 1.0**（或约定阈值） |
| `source_grounding_rate` | 事实数值能在原文定位 | **必须 ≥ 0.95** |
| `source_table_grounding_rate` | 数值落在绑定源表 | 建议 ≥ 0.8 |
| `implausible_period_ratio` | 脏期间 | **必须 ≈ 0** |
| `provenance_metric_ratio` | 带来源表/页 | 建议 = 1.0 |
| `statements_with_metrics_ratio` | 无空壳 statement | 建议 = 1.0 |

Golden 策略（少而精）：

- 每份样本文档 **5–15 个核心字段**（营收、净利、经营现金流、总资产等）
- 文件：`data/golden/*_stage_expectations.json`
- 可选扩展：外部伪 golden（巨潮/东财），用于查漏，不替代原文回查

**L2 未过 → 禁止写入 Postgres 指标表 / Neo4j Metric 边。**  
（segments 是否进 Qdrant 可另定宽松闸门，见 §4）

### L3 — 检索可用（入库后的第一道验收）

固定题集（per document），三类路由都要覆盖：

| 题型 | 期望路由 | 成功标准 |
|------|----------|----------|
| 「2021 年营业收入是多少」 | `structured` | SQL 命中正确值 + 期间 |
| 「管理层如何评价主营业务」 | `semantic` | Top-K 含 MD&A 相关段 |
| 「营收为何增长」 | `hybrid` | 有数 + 有叙述证据，且数一致 |

建议指标（待脚本化）：

- `structured_hit@1`：结构化题是否答对数值  
- `semantic_recall@k`：应含章节/关键词是否出现在 Top-K  
- `citation_grounding`：返回证据能否指回 page/table/segment_id  
- `conflict_warning_rate`：同指标多值冲突时是否告警（见 trend API）

### L4 — 研究闭环（产品层）

对应 `POST /api/v1/research/query` + Critic：

| 指标 | 含义 |
|------|------|
| `grounded=true` 率 | Critic 通过比例 |
| 数字幻觉率 | 答案中数字不在 V/S/C 证据目录的比例（↓） |
| 引用完整率 | 关键论断带 evidence id |
| 降级透明率 | 失败时 `grounded=false` 且有 warnings |

**批量脚本阈值**（`scripts/run_l4_research_eval.py`，见 `docs/acceptance_suite.md`）：

| 闸 | 阈值 |
|----|------|
| retrieval-only（znz/聚灿/天华） | `pass_rate == 1.0` |
| full · smoke（znz） | `pass_rate == 1.0`（不回归） |
| full · regression（聚灿/天华） | `pass_rate >= 0.8`（软闸） |

多样本：`--profile smoke|regression|all` → 汇总 `data/reports/l4_eval/latest_l4_summary.json`。

L4 依赖 L2+L3；解析再好，检索证据错也会在 L4 暴露。

---

## 3. 与现有实现的映射

| 层级 | 已有能力 | 缺口 |
|------|----------|------|
| L0/L1/L2 | `StageScorecardService` + `run_stage_eval.py` + `source_grounding`；3 个 ready 样本 | Stress/外部伪 golden |
| L2 扩展 | `ParseEvaluationBenchmarkService` / `DocumentAIGoldenEvaluator` | 与 scorecard 统一入口 |
| L3 | `RetrievalOrchestrator` + `run_serving_ingest_eval.py`；指南针/聚灿/天华全绿；真实跨文档冲突、扫描 OCR 与复杂表 Stress 已建 | 公告/研报混合来源冲突；极端低清/旋转图像 |
| L4 | Grounded synthesis + critic；批量 `--profile` 与汇总报告 | 三样本 full 题集 100%，已进入 acceptance 发布硬门禁 |

当前指南针 2021：L2/L3 闸门已通；L4 full znz 曾达 8/8。聚灿/天华可用 `--profile regression` 扩评。

---

## 4. 入库闸门策略（先定规则，再写代码）

### 4.1 允许写入的对象

| 对象 | 目标库 | 闸门 |
|------|--------|------|
| `metric_facts`（核心/全量结构化） | Postgres / Neo4j | L2 硬闸门通过；仅写入 `source_grounding` 为真的 facts（推荐） |
| `segments` | Qdrant + segment repo | L1：`tiny_segment_ratio` 可接受；可选丢弃 TOC/过短段 |
| 图谱非 Metric 边（Risk/Document） | Neo4j | 有 `document_id` + evidence；Metric 边仍受 L2 约束 |
| 原始 PDF / parsed JSON | 对象存储 / local | 始终可存（审计用），与「事实库」分离 |

### 4.2 推荐写入策略

1. **双轨存储**  
   - *Artifact 轨*：完整 `ParsedDocument`（调试/重跑）  
   - *Serving 轨*：通过闸门的 metrics + 清洁 segments  
2. **Serving 轨默认过滤**  
   - 无 provenance 的 metric 不进 Postgres  
   - `source_grounding` 失败的 metric 不进图谱  
   - tiny/TOC segment 不进 Qdrant  
3. **冲突处理**  
   - 同 `(company, metric_key, period)` 多值 → 保留带 provenance 且 grounding 成功者；否则写入 warning，不静默覆盖  

### 4.3 放行清单（单文档）

入库 Serving 轨前，自动化检查应全部为真：

- [ ] `core_metric_exact_match == 1.0`（相对该文档 golden）  
- [ ] `source_grounding_rate >= 0.95`  
- [ ] `implausible_period_ratio == 0`  
- [ ] `statements_with_metrics_ratio == 1.0`  
- [ ] 文档 `company` / `year` 元数据非空  

---

## 5. 样本与 Golden 规范

### 5.1 样本集分层

| 集合 | 规模 | 用途 |
|------|------|------|
| Smoke | 1 份（指南针 2021） | 每次改动必跑；见 `docs/acceptance_suite.md` |
| Regression | 2–5 份 A 股年报 | 合并前必跑；第二份=`jucan_2021_stage_expectations.json`（ready） |
| Stress | 共同药业扫描件 OCR + 第 86 页复杂表 | route/backend、文字/关键短语、表头/行/原页码/provenance |

### 5.2 Golden 文件最小字段

```json
{
  "document_key": "znz_2021_annual_report",
  "required_semantic_section_types": ["management_discussion", "financial_statement", "company_overview"],
  "core_metrics": {
    "revenue": {"2021": 931944638, "2020": 691620925},
    "net_cash_from_operating_activities": {"2021": 373048933, "2020": 230581891}
  },
  "retrieval_cases": [
    {
      "id": "q_revenue_2021",
      "question": "2021年营业收入是多少？",
      "expect_route": "structured",
      "expect_metric_key": "revenue",
      "expect_period": "2021",
      "expect_value": 931944638
    }
  ]
}
```

`retrieval_cases` 由 `scripts/run_serving_ingest_eval.py` 在 Serving 入库后自动评分。

---

## 6. 判定总则

1. **覆盖率 ≠ 准确率**：表多、段多、节点多都不算成功。  
2. **硬指标优先**：核心 golden 与 grounding 下降 → 一律负向，即使其它指标变好。  
3. **分层放行**：L2 不过不进事实库；L3 不过不宣称「检索可用」；L4 不过不宣称「可可信回答」。  
4. **同文档对比**：改动前后用同一 PDF + 同一 golden，避免样本漂移。  

---

## 7. 建议推进顺序（评估 → 入库）

| 顺序 | 做什么 | 产出 | 状态 |
|------|--------|------|------|
| ① 固化本文 | 评审通过本评估体系 | `docs/evaluation_system.md` | ✔ |
| ② 扩展 golden | 核心字段 + `retrieval_cases` + `serving_gate` | `data/golden/znz_2021_stage_expectations.json` | ✔ |
| ③ 入库闸门代码 | `ServingGateService` 接入 pipeline index/graph | `evaluation/serving_gate.py` | ✔ |
| ④ 打通 Serving 入库 | Postgres metrics + Qdrant segments + Neo4j | 单文档 E2E | ✔ |
| ⑤ L3 题集脚本 | 按 `retrieval_cases` 自动打分（含 graph） | `scripts/run_serving_ingest_eval.py` | ✔ 硅基 embedding 复验 pass_rate=1.0（8/8） |
| ⑥ L4 批量 eval | `--profile` 多样本 + 阈值文档 | 需可用 LLM / Docker | ✅ 脚本就绪；full 跑时需 LLM |

### Serving 入库命令

```bash
docker compose up -d postgres qdrant neo4j
# 默认要求 Silicon embedding 可用（402/缺 key 直接失败，不落 hash）
python scripts/run_serving_ingest_eval.py --storage-backend postgres --vector-backend qdrant --graph-backend neo4j
# 仅离线调试才允许：
# python scripts/run_serving_ingest_eval.py --allow-hash-fallback
```

报告：`data/reports/serving_eval/*_serving_eval.json`

要点：

- Artifact payload 保留全量 facts；`financial_items` / Local SQL 只读 Serving 闸门放行的 facts（`app/core/db/serving_facts.py`）
- L3 评路由 + 结构化数值 + 语义关键词 + graph 关系类型（`expect_graph_relation_types`），不依赖 LLM 合成（L4 另算）
- 生产复验条件：`EMBEDDING_BACKEND=silicon`、`SILICON_KEY` 有效、返回向量维 = `EMBEDDING_DIMENSIONS`（默认 1024）、collection=`document_segments_bge_m3`

### 已落地的闸门行为

- **Artifact 轨**：完整 `ParsedDocument` 始终落盘（含 `financial_schema.metadata.serving_gate`）
- **Serving 轨**：`DocumentPipelineService` 在 index/graph 前调用 `ServingGateService.apply_to_document`
  - metric 未过闸 → 图谱不写 Metric facts
  - segment 过宽松闸 → 过滤 TOC/过短块后再进向量/segment repo
- Stage eval 输出 `serving_gate`；未过 metric 闸时 exit code `3`

---

## 8. 相关文件

- 验收套件（命令 / 通过标准）：`docs/acceptance_suite.md`  
- 指标定义（L1/L2 细节）：`docs/eval_metrics.md`  
- 当前样本快照：`docs/pipeline_eval_status.md`  
- Stage 跑分：`scripts/run_stage_eval.py`  
- 一键验收：`scripts/run_acceptance_suite.py`  
- 实现：`app/pipeline/feature_pipeline/evaluation/`  
- 检索/研究 API：`docs/structured_financial_data_api.md`  
- 图谱：`docs/knowledge_graph.md`  
