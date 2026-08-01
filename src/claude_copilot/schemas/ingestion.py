from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class IngestionJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionJobEvent(BaseModel):
    timestamp: datetime
    status: IngestionJobStatus
    stage: str | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    message: str | None = None


class IngestionJob(BaseModel):
    job_id: str
    doc_id: str
    filename: str
    status: IngestionJobStatus = IngestionJobStatus.QUEUED
    stage: str = "waiting"
    progress_percent: int = Field(default=0, ge=0, le=100)
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    available_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    error_message: str | None = None
    events: list[IngestionJobEvent] = Field(default_factory=list)


class IngestionBatchResponse(BaseModel):
    jobs: list[IngestionJob] = Field(default_factory=list)


class IngestionQueueAlert(BaseModel):
    code: str
    severity: Literal["warning", "critical"]
    message: str
    observed_value: float
    threshold: float


class IngestionQueueMetrics(BaseModel):
    generated_at: datetime
    status_counts: dict[IngestionJobStatus, int]
    active_worker_count: int = Field(ge=0)
    cancellation_requested_count: int = Field(ge=0)
    oldest_ready_age_seconds: float | None = Field(default=None, ge=0)
    expired_lease_count: int = Field(default=0, ge=0)
    recent_failed_count: int = Field(default=0, ge=0)
    health_status: Literal["ok", "warning", "critical"] = "ok"
    alerts: list[IngestionQueueAlert] = Field(default_factory=list)
