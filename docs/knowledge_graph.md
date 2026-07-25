# Knowledge Graph / GraphRAG MVP

项目已经具备从解析文档到图检索证据的最小闭环：

```text
ParsedDocument + FinancialSchema
  -> KnowledgeGraphBuilder
  -> Local JSON / Neo4j
  -> RetrievalOrchestrator
  -> GraphPath (G1, G2...)
  -> Grounded Research + Critic
```

## 图模型

节点类型：

- `Company`
- `Subsidiary`
- `Industry`
- `BusinessSegment`
- `Event`
- `Document`
- `Metric`
- `Risk`

关系类型：

- `HAS_DOCUMENT`
- `REPORTS_METRIC`
- `HAS_RISK`
- `OWNS`
- `OPERATES_IN`
- `AFFECTED_BY`
- `COMPETES_WITH`
- `EVIDENCED_BY`

每条关系都包含 `document_id`、`page_range`、`evidence_text` 和 `confidence`。
实体名称经过 Unicode、标点、空格和公司法律后缀归一化；同一公司的不同写法会生成相同
`company_id`。共享实体保存 `years`、`document_ids` 和 `aliases`，用于跨年度合并。

## 存储后端

本地开发默认使用 JSON：

```env
GRAPH_STORE_BACKEND=local
GRAPH_DATA_PATH=./data/graph
```

Neo4j：

```env
GRAPH_STORE_BACKEND=neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=claude-copilot
NEO4J_DATABASE=neo4j
```

启动 Neo4j：

```bash
docker compose up -d neo4j
```

浏览器管理界面：`http://localhost:7474`

## 数据写入与回填

新上传文档会在向量索引阶段同步重建对应文档的图数据。

将已有的 completed 文档回填到当前图后端：

```bash
uv run python scripts/backfill_knowledge_graph.py
```

## 查询

查看单份文档的完整图：

```http
GET /api/v1/documents/{doc_id}/knowledge-graph
```

查看同一公司跨年度合并后的图：

```http
GET /api/v1/companies/{company_id}/knowledge-graph
```

上传时可以提供高置信度行业和公司别名：

```text
industry=banking
company_aliases=JPMorganChase,JPMC
```

Research 查询包含风险、关系、关联、暴露或影响等意图时，检索调度器会启用
`graph` 路由。返回结果中的 `graph_paths` 会同时作为 `G*` 证据进入回答生成与审校。

## 当前边界

这是 GraphRAG MVP，不是完整企业知识图谱。当前实体抽取以财务 Schema 和确定性风险分类为
基础；当前子公司、竞争对手和事件采用确定性模式抽取，下一阶段仍需引入受 Schema 约束的
LLM 抽取、人工评测集、图算法和自动多跳查询规划。
