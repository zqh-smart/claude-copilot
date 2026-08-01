CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    storage_path TEXT NOT NULL,
    parsed_path TEXT,
    segment_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS ix_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS ix_documents_metadata_gin ON documents USING GIN(metadata);

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

CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_doc_id ON ingestion_jobs(doc_id);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_status ON ingestion_jobs(status);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_created_at ON ingestion_jobs(created_at);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_status_updated_at ON ingestion_jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_worker_id ON ingestion_jobs(worker_id);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_lease_expires_at ON ingestion_jobs(lease_expires_at);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_available_at ON ingestion_jobs(available_at);

CREATE TABLE IF NOT EXISTS parsed_documents (
    doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_parsed_documents_payload_gin ON parsed_documents USING GIN(payload);

CREATE TABLE IF NOT EXISTS parsed_tables (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    table_index INTEGER NOT NULL,
    table_id TEXT,
    table_type TEXT,
    title TEXT,
    page INTEGER,
    raw_markdown TEXT,
    headers JSONB NOT NULL DEFAULT '[]'::jsonb,
    rows JSONB NOT NULL DEFAULT '[]'::jsonb,
    period_headers JSONB NOT NULL DEFAULT '[]'::jsonb,
    unit TEXT,
    currency TEXT,
    note_number TEXT,
    note_title TEXT,
    note_category TEXT,
    semantic_rows JSONB NOT NULL DEFAULT '[]'::jsonb,
    normalized_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(doc_id, table_index)
);

CREATE INDEX IF NOT EXISTS ix_parsed_tables_doc_id ON parsed_tables(doc_id);
CREATE INDEX IF NOT EXISTS ix_parsed_tables_table_type ON parsed_tables(table_type);
CREATE INDEX IF NOT EXISTS ix_parsed_tables_note_category ON parsed_tables(note_category);
CREATE INDEX IF NOT EXISTS ix_parsed_tables_headers_gin ON parsed_tables USING GIN(headers);
CREATE INDEX IF NOT EXISTS ix_parsed_tables_rows_gin ON parsed_tables USING GIN(rows);
CREATE INDEX IF NOT EXISTS ix_parsed_tables_period_headers_gin ON parsed_tables USING GIN(period_headers);
CREATE INDEX IF NOT EXISTS ix_parsed_tables_semantic_rows_gin ON parsed_tables USING GIN(semantic_rows);
CREATE INDEX IF NOT EXISTS ix_parsed_tables_normalized_metrics_gin ON parsed_tables USING GIN(normalized_metrics);
CREATE INDEX IF NOT EXISTS ix_parsed_tables_metadata_gin ON parsed_tables USING GIN(metadata);

CREATE TABLE IF NOT EXISTS financial_items (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    source_table_id TEXT,
    fact_type TEXT NOT NULL,
    metric_key TEXT,
    fact_key TEXT,
    statement_type TEXT,
    period TEXT,
    value_numeric NUMERIC,
    value_text TEXT,
    unit TEXT,
    currency TEXT,
    note_number TEXT,
    note_title TEXT,
    note_category TEXT,
    row_label TEXT,
    row_type TEXT,
    dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_section TEXT,
    page_range JSONB,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_financial_items_doc_id ON financial_items(doc_id);
CREATE INDEX IF NOT EXISTS ix_financial_items_fact_type ON financial_items(fact_type);
CREATE INDEX IF NOT EXISTS ix_financial_items_metric_key ON financial_items(metric_key);
CREATE INDEX IF NOT EXISTS ix_financial_items_fact_key ON financial_items(fact_key);
CREATE INDEX IF NOT EXISTS ix_financial_items_statement_type ON financial_items(statement_type);
CREATE INDEX IF NOT EXISTS ix_financial_items_period ON financial_items(period);
CREATE INDEX IF NOT EXISTS ix_financial_items_note_category ON financial_items(note_category);
CREATE INDEX IF NOT EXISTS ix_financial_items_doc_metric_period
    ON financial_items(doc_id, metric_key, period);
CREATE INDEX IF NOT EXISTS ix_financial_items_dimensions_gin ON financial_items USING GIN(dimensions);
CREATE INDEX IF NOT EXISTS ix_financial_items_tags_gin ON financial_items USING GIN(tags);
CREATE INDEX IF NOT EXISTS ix_financial_items_page_range_gin ON financial_items USING GIN(page_range);
CREATE INDEX IF NOT EXISTS ix_financial_items_provenance_gin ON financial_items USING GIN(provenance);

CREATE TABLE IF NOT EXISTS document_segments (
    segment_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    parent_section_id TEXT,
    position INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_summary TEXT,
    keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(doc_id, position)
);

CREATE INDEX IF NOT EXISTS ix_document_segments_doc_id ON document_segments(doc_id);
CREATE INDEX IF NOT EXISTS ix_document_segments_position ON document_segments(position);
CREATE INDEX IF NOT EXISTS ix_document_segments_keywords_gin ON document_segments USING GIN(keywords);
CREATE INDEX IF NOT EXISTS ix_document_segments_metadata_gin ON document_segments USING GIN(metadata);
CREATE INDEX IF NOT EXISTS ix_document_segments_search_vector_gin ON document_segments USING GIN(search_vector);
