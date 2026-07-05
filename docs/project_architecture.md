# Claude Copilot Project Architecture

## 1. 目标

本文档是 `claude_copilot` 的首版工程架构说明，目标是把现有参考分析文档落到实际目录与模块边界上。

当前明确采用的原则如下：

1. 主框架优先选择 LangGraph。
2. 优先借鉴 `Bank-copilot-main` 的金融分析工程组织方式。
3. 重点吸收 Dify 在文档处理链路上的完整设计。
4. 从第一版开始预留 LangSmith 与 Langfuse 观测能力。

## 2. 为什么主框架是 LangGraph

这个项目不是单轮问答，也不是简单的知识库封装，而是金融文档驱动的分析系统。后续会稳定出现这些需求：

- 多步骤推理
- 条件分支与回退
- 工具调用
- 长链路状态管理
- 多 Agent 协作
- 人工审核插入

这类问题更适合由 LangGraph 承担主编排层，而不是把流程写成松散链式调用。

## 3. 为什么优先借鉴 Bank，再吸收 Dify

`Bank-copilot-main` 更接近金融场景应用本身，适合借鉴：

- `app/api`
- `app/core`
- `app/pipeline`
- `app/core/rag`
- `app/core/kg`
- 面向金融分析任务的模块划分方式

Dify 更适合借鉴文档工程化部分，尤其是：

- parser / extractor router
- 文档状态机
- segment 持久化
- parent-child chunk
- summary index
- 异步任务、重试与恢复

因此当前路线不是复制任一项目，而是明确分工：

- Bank 提供金融应用结构参考
- Dify 提供文档处理底座参考
- LangGraph 提供主编排能力

## 4. 当前目录结构

```text
claude_copilot/
├── app/
│   ├── api/                         # FastAPI 路由与服务入口
│   ├── core/                        # 配置、观测、RAG、DB、KG、Prompts
│   │   ├── db/
│   │   ├── kg/
│   │   ├── prompts/
│   │   └── rag/
│   ├── pipeline/                    # 文档处理与索引流水线
│   │   └── feature_pipeline/
│   │       ├── chunking/
│   │       ├── indexing/
│   │       └── parser/
│   └── workflows/                   # LangGraph 工作流
│       ├── reporting/
│       ├── research/
│       └── risk/
├── src/
│   └── claude_copilot/              # 可复用领域包与 schema
├── tests/
├── data/
│   ├── documents/
│   ├── fixtures/
│   ├── parsed/
│   ├── raw/
│   └── reports/
├── docs/
├── .env.example
└── pyproject.toml
```

## 5. 目录职责说明

### `app/api/`

对外 API 层。当前只保留健康检查，后续扩展：

- 文档上传
- 文档处理状态查询
- 检索接口
- 分析接口
- 报告生成接口

### `app/core/`

核心能力层，优先参考 `Bank-copilot-main` 的后端组织方式。

当前预留：

- `config.py`：统一配置入口
- `observability.py`：LangSmith / Langfuse 接入入口
- `db/`：数据库、向量库、对象存储适配层
- `rag/`：检索增强模块
- `kg/`：图谱与关系建模模块
- `prompts/`：提示词模板与版本管理

### `app/pipeline/feature_pipeline/`

这是当前阶段最重要的工程骨架，直接对应“优先借鉴 Dify 文档链路 + 借鉴 Bank 的 pipeline 组织方式”。

当前按三块预留：

- `parser/`
  - parser router
  - PDF / OCR / Office / HTML 等 extractor 适配
- `chunking/`
  - 章节切分
  - parent-child chunk
  - 表格与段落切分
- `indexing/`
  - segment 持久化
  - embedding
  - 向量索引写入

同时保留 `state_machine.py`，用于承接文档处理状态流转：

- waiting
- parsing
- cleaning
- chunking
- indexing
- completed
- failed
- paused

### `app/workflows/`

LangGraph 工作流层。

当前先按业务目标预留三个方向：

- `research/`：投研分析
- `risk/`：风险识别与归因
- `reporting/`：报告生成与交付

### `src/claude_copilot/`

领域模型与可复用包代码。当前已提供文档 schema，后续继续扩展：

- 文档对象
- 金融实体对象
- 指标对象
- 风险对象
- 报告对象

### `data/`

本地开发数据分层，避免原始文档、解析结果和最终报告混放：

- `raw/`：原始输入文档
- `documents/`：上传后归档文档
- `parsed/`：解析后的结构化结果
- `reports/`：输出报告
- `fixtures/`：测试样本

## 6. 本次骨架已经落地的内容

当前已完成：

- README 项目介绍页
- `app/`, `src/`, `tests/`, `data/` 基础目录
- FastAPI 启动入口与 `/health`
- `pydantic-settings` 配置入口
- LangSmith / Langfuse 观测占位配置
- 文档 schema
- 首个测试用例
- 首版 `project_architecture.md`
- `pyproject.toml`
- `.env.example`

## 7. 当前优先借鉴点的工程映射

| 来源 | 借鉴内容 | 当前工程映射 |
| --- | --- | --- |
| Bank-copilot-main | 后端目录分层 | `app/api/`, `app/core/`, `app/pipeline/`, `app/workflows/` |
| Bank-copilot-main | RAG 模块边界 | `app/core/rag/` |
| Bank-copilot-main | DB / KG 扩展方向 | `app/core/db/`, `app/core/kg/` |
| Bank-copilot-main | Prompt 与推理组织方式 | `app/core/prompts/`, `app/workflows/` |
| Dify | parser router | `app/pipeline/feature_pipeline/parser/` |
| Dify | 文档状态机 | `app/pipeline/feature_pipeline/state_machine.py` |
| Dify | chunking 体系 | `app/pipeline/feature_pipeline/chunking/` |
| Dify | segment 持久化与索引 | `app/pipeline/feature_pipeline/indexing/` |
| Dify | 数据分层思路 | `data/raw/`, `data/parsed/`, `data/reports/` |

## 8. 下一步建议

下一轮建议按下面顺序推进：

1. 建立文档上传接口与文件落盘策略
2. 实现 parser router 骨架
3. 统一 `ParsedDocument` 输出协议
4. 实现 chunking 与 segment 持久化
5. 接入向量索引
6. 接入第一个 LangGraph workflow
7. 接入 LangSmith / Langfuse tracing

这样可以保证：

- 结构稳定
- 每层可测试
- 文档底座先成型
- 金融分析能力后续可平滑叠加
