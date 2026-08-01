# Document Ingestion Jobs

文档上传现在支持“归档与处理分离”的异步任务模式。文件在请求内完成持久化，解析、清洗、
Schema、切分、索引和知识图谱随后由后台执行器处理。

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/documents/upload/async` | 上传一个文件并返回任务 |
| `POST` | `/api/v1/documents/upload/batch/async` | 批量上传并返回一组任务 |
| `GET` | `/api/v1/documents/jobs` | 查询最近任务 |
| `GET` | `/api/v1/documents/jobs/metrics` | 查询状态计数、Worker 与等待时间指标 |
| `GET` | `/api/v1/documents/jobs/{job_id}` | 查询阶段、进度和事件轨迹 |
| `POST` | `/api/v1/documents/jobs/{job_id}/retry` | 手动重试失败或取消的任务 |
| `POST` | `/api/v1/documents/jobs/{job_id}/cancel` | 取消排队任务，或请求运行中任务在阶段边界停止 |

原有 `POST /api/v1/documents/upload` 保留为同步兼容接口。内部工作台上传默认使用异步接口。

## 状态与恢复

任务状态：

```text
queued → running → succeeded
              └→ retry_wait → queued
              └→ failed
queued/retry_wait → cancelled
```

任务独立记录 `stage`、百分比、尝试次数、错误和事件时间线。API 进程重新启动后，首次创建
任务服务时会重新调度 `queued`、`running` 和 `retry_wait` 任务。若文档停留在解析、清洗、
切分或索引阶段，流水线会先转为 paused，再从 parsing 重新执行；下游写入按 `doc_id` 替换，
因此重试不会创建重复文档。

## 存储后端

- Local：`data/parsed/ingestion_jobs.json`，线程安全且原子替换写入。
- PostgreSQL：`ingestion_jobs` 表。新环境由 `scripts/init_postgres.sql` 创建；已有数据库执行：

```powershell
Get-Content scripts/migrations/20260801_ingestion_jobs.sql -Raw |
  docker compose exec -T postgres psql -U postgres -d claude_copilot
```

## 当前边界与后续

当前执行器仍由 API 进程内的 `ThreadPoolExecutor` 驱动；持久化任务状态、自动重试、重启恢复、
Repository 原子领取、Worker 租约、周期心跳、租约超时接管和旧 Worker fencing 已经可用。
Local 并发测试与真实 PostgreSQL 双 Worker 领取测试均已覆盖。

独立 Worker 入口已经提供：

```powershell
# API 进程只归档并创建 queued 任务
$env:INGESTION_INLINE_EXECUTION_ENABLED='false'
uv run uvicorn app.main:app --reload

# 独立进程轮询并原子领取任务
$env:INGESTION_INLINE_EXECUTION_ENABLED='false'
$env:INGESTION_WORKER_ID='worker-a' # 每个部署实例设置唯一稳定 ID
uv run python scripts/run_ingestion_worker.py --poll-seconds 1
```

`retry_wait` 使用持久化 `available_at`，因此进程重启不会丢失延迟重试。Redis 可用于后续唤醒与
队列优化，但任务所有权仍以 PostgreSQL 租约为准，避免双重真相源。

运行中任务支持持久化取消请求；Worker 在下一流水线阶段边界停止，任务进入 `cancelled`，文档
进入 `paused`，且不会触发失败重试。工作台任务页展示状态计数、活跃 Worker、待取消数和最老
可执行任务等待时间。

`GET /jobs/metrics` 同时提供机器可读告警契约：`health_status`（ok/warning/critical）、
`expired_lease_count`、`recent_failed_count` 与 `alerts[]`。内置规则覆盖过期 Worker 租约、近期失败、
最老可执行任务等待过久和 retry-wait 积压；阈值由以下环境变量配置：

```text
INGESTION_ALERT_OLDEST_READY_SECONDS=300
INGESTION_ALERT_RETRY_WAIT_COUNT=5
INGESTION_ALERT_RECENT_FAILURE_COUNT=1
INGESTION_ALERT_FAILURE_WINDOW_SECONDS=3600
```

工作台直接展示告警；部署平台可轮询该端点并将 `critical`/`warning` 接入 Prometheus、Pager、
邮件或企业 IM，通知渠道不在应用内形成第二套任务状态源。

独立 Worker PostgreSQL soak 已提供并复验：

```powershell
uv run python scripts/run_ingestion_worker_soak.py
# 默认 3 轮 × 8 任务，每轮重启两个 Worker 进程
```

通过条件为 24/24 succeeded、全部 `attempt == 1`、至少两个进程实际领取、文档全部
completed、租约全部释放、子进程全部正常退出。2026-08-01 实测 24/24 通过，6 个 Worker
实例均有实际领取，耗时 10.875 秒。部署环境只需按平台选择日志采集与告警通知渠道。

内部工作台“处理任务”页直接读取上述任务 API，不使用人工进度标记。
