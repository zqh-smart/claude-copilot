# Claude Copilot

Financial document intelligence system based on LangGraph.

## 项目定位

Claude Copilot 面向金融文档智能分析场景，当前重点是先把文档处理底座做完整，再逐步接入金融分析、研究和报告生成能力。

当前技术路线：

- 主框架：LangGraph
- 观测：LangSmith + Langfuse
- 文档处理参考：Dify
- 金融分析工程组织参考：Bank-copilot-main

## 当前重点

第一阶段优先解决：

- 文档上传与处理状态流转
- PDF / DOCX / Markdown 解析
- PDF 路由：`native_pdf` / `ocr_pdf` / `table_pdf` / `mineru_pdf`
- 页面结构、表格结构、chunking
- 向量化索引与检索基础设施

## 默认工作流：uv

本项目默认使用 `uv` 管理 Python 环境、依赖和锁文件。

### 1. 创建虚拟环境

```bash
uv venv
```

### 2. 激活环境

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. 安装依赖

基础开发依赖：

```bash
uv sync
```

带 PDF OCR 和 MinerU：

```bash
uv sync --extra pdf_ocr --extra pdf_mineru
```

### 4. 复制环境变量

```powershell
Copy-Item .env.example .env
```

### 5. 运行测试

```bash
uv run pytest -q
```

### 6. 启动服务

```bash
uv run uvicorn app.main:app --reload
```

启动后可访问：

- `GET /health`

## 本地启动：Silicon / Qdrant / Postgres

当前本地默认使用：

- SiliconFlow：Embedding + Rerank
- PostgreSQL：结构化文档、解析结果、segment 持久化
- Qdrant：向量索引与检索
- Redis：预留给缓存 / 异步任务

### 1. 启动基础容器

```bash
docker compose up -d
```

可检查容器状态：

```bash
docker compose ps
```

### 2. 准备本地环境变量

如需从模板创建：

```powershell
Copy-Item .env.example .env
```

当前推荐的关键配置如下：

```env
STORAGE_BACKEND=postgres
VECTOR_STORE_BACKEND=qdrant
POSTGRES_DSN=postgresql+psycopg://postgres:postgres@localhost:5432/claude_copilot
QDRANT_URL=http://localhost:6333
QDRANT_GRPC_PORT=6334
QDRANT_COLLECTION_NAME=document_segments_bge_m3
EMBEDDING_BACKEND=silicon
EMBEDDING_MODEL_ID=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024
RERANK_BACKEND=silicon
RERANK_MODEL_ID=BAAI/bge-reranker-v2-m3
SILICON_BASE_URL=https://api.siliconflow.cn/v1
SILICON_KEY=your_key_here
```

### 3. 启动 API

```bash
uv run uvicorn app.main:app --reload
```

### 4. 健康检查

Qdrant：

```bash
curl http://localhost:6333/healthz
```

FastAPI：

```bash
curl http://localhost:8000/health
```

### 5. 历史文档回填到新向量索引

当你切换到 `bge-m3` 这一套 1024 维 embedding 后，旧 collection 不应继续复用。当前默认 collection 为：

- `document_segments_bge_m3`

如需把历史 `completed` 文档重新写入该 collection：

```bash
uv run python scripts/backfill_qdrant.py
```

该脚本会：

- 跳过 `failed` 文档
- 优先读取 `parsed_documents` 中的 `segments`
- 必要时回退到结构化 `document_segments`
- 对每个 `doc_id` 执行 Qdrant 先删后写

### 6. 本地快速验证检索链

在本地完成容器启动、`.env` 配置和历史回填后，可直接运行历史文档检索 smoke test：

```bash
uv run python scripts/run_retrieval_smoke.py
```

该脚本会：

- 读取当前所有 `completed` 文档
- 按内置问题模板执行 research preview 检索
- 输出每个文档的 top hits、分数和命中文本摘要
- 将结果写入 `data/reports/historical_retrieval_smoke_report.json`

## 可选依赖

`pyproject.toml` 里已经定义：

- `pdf_ocr`
  - `pymupdf`
  - `pillow`
  - `pytesseract`
- `pdf_mineru`
  - `mineru`

如果要启用真实 OCR / MinerU 解析，请安装对应 extra。

## 当前目录结构

```text
claude_copilot/
├─ app/                         # 运行时入口与服务编排
│  ├─ api/                      # FastAPI 路由
│  ├─ core/                     # 配置、观测、RAG、DB 等核心模块
│  └─ pipeline/                 # 文档处理与索引流水线
├─ src/
│  └─ claude_copilot/           # schema 与可复用领域模型
├─ tests/                       # 测试
├─ data/                        # 本地数据、样例与解析产物
├─ docs/                        # 设计与参考文档
├─ .env.example
├─ pyproject.toml
└─ uv.lock
```

## 文档

- [docs/Financial Document Intelligenc....md](docs/Financial%20Document%20Intelligenc....md)
- [docs/claude_copilot_project_references_and_langgraph_strategy.md](docs/claude_copilot_project_references_and_langgraph_strategy.md)
- [docs/project_architecture.md](docs/project_architecture.md)
- [docs/knowledge_graph.md](docs/knowledge_graph.md)

## Knowledge Graph / GraphRAG MVP

文档流水线会从 `FinancialSchema` 构建 Company、Document、Metric、Risk 节点，并写入本地
JSON 或 Neo4j。Research 检索调度器可以把图路径与 Qdrant、SQL 证据一起交给回答和 Critic。

已有文档回填：

```bash
uv run python scripts/backfill_knowledge_graph.py
```

具体配置与接口见 [docs/knowledge_graph.md](docs/knowledge_graph.md)。

## 当前状态

已经具备：

- `uv` 环境与锁文件
- 基础 API 骨架
- 文档处理流水线
- PDF 四类路由
- 结构化 `page_blocks` / `tables`
- 基础测试集

下一步重点是继续做真实 PDF 联调、提升 MinerU 适配质量，以及补全更完整的金融文档样本测试。
