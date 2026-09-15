CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'waiting',
    progress_percent INTEGER NOT NULL DEFAULT 0,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    worker_id TEXT,
    heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ,
    cancel_requested_at TIMESTAMPTZ,
    error_message TEXT,
    events JSONB NOT NULL DEFAULT '[]'::jsonb
);

ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS worker_id TEXT;
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ;
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS cancel_requested_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_doc_id ON ingestion_jobs(doc_id);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_status ON ingestion_jobs(status);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_created_at ON ingestion_jobs(created_at);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_status_updated_at ON ingestion_jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_worker_id ON ingestion_jobs(worker_id);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_lease_expires_at ON ingestion_jobs(lease_expires_at);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_available_at ON ingestion_jobs(available_at);
