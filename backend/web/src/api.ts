const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

async function requestArtifact(path: string, init: RequestInit): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? "research-report";
  return { blob: await response.blob(), filename };
}

export type DocumentRecord = {
  doc_id: string;
  filename: string;
  status: string;
  segment_count: number;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  metadata: {
    company?: string | null;
    year?: number | null;
    doc_type?: string | null;
    industry?: string | null;
    company_aliases?: string[] | null;
  };
};

export type DocumentSegment = {
  segment_id: string;
  document_id: string;
  parent_section_id?: string | null;
  position: number;
  content: string;
  content_summary?: string | null;
  keywords?: string[];
  metadata?: Record<string, unknown> | null;
};

export type KnowledgeGraphNode = {
  node_id: string;
  node_type: string;
  name: string;
  document_id?: string | null;
  properties?: Record<string, unknown>;
};

export type KnowledgeGraphRelationship = {
  relationship_id: string;
  relationship_type: string;
  source_node_id: string;
  target_node_id: string;
  document_id: string;
  evidence_text?: string | null;
  confidence?: number;
  properties?: Record<string, unknown>;
};

export type DocumentKnowledgeGraph = {
  document_id: string;
  company_id?: string | null;
  nodes: KnowledgeGraphNode[];
  relationships: KnowledgeGraphRelationship[];
};

export type IngestionJobEvent = {
  timestamp: string;
  status: string;
  stage?: string | null;
  progress_percent: number;
  message?: string | null;
};

export type IngestionJob = {
  job_id: string;
  doc_id: string;
  filename: string;
  status: string;
  stage: string;
  progress_percent: number;
  attempt: number;
  max_attempts: number;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  events: IngestionJobEvent[];
};

export type IngestionQueueMetrics = {
  generated_at: string;
  status_counts: Record<string, number>;
  active_worker_count: number;
  cancellation_requested_count: number;
  oldest_ready_age_seconds?: number | null;
  expired_lease_count: number;
  recent_failed_count: number;
  health_status: "ok" | "warning" | "critical";
  alerts: Array<{
    code: string;
    severity: "warning" | "critical";
    message: string;
    observed_value: number;
    threshold: number;
  }>;
};

export type CompanySummary = {
  company_id: string;
  name: string;
  document_count?: number;
  years?: number[];
};

export type MetricObservation = {
  metric_key: string;
  period: string;
  value: number | string;
  statement_type?: string | null;
  document_id?: string | null;
};

export type MetricTrend = {
  company: CompanySummary;
  metric_key: string;
  unit?: string | null;
  currency?: string | null;
  points: Array<{
    year: number;
    period: string;
    value: number;
    yoy_growth?: number | null;
    document_id: string;
  }>;
  cagr?: number | null;
  warnings: string[];
};

export type CompareResponse = {
  answer_markdown: string;
  matrix: Array<Record<string, unknown>>;
  highlights: string[];
  warnings: string[];
  workflow: string;
};

export type ReportOutlineResponse = {
  answer_markdown: string;
  sections: Array<Record<string, unknown>>;
  warnings: string[];
  workflow: string;
};

export type PortfolioDashboard = {
  company_ids: string[];
  rankings: Array<{
    metric_key: string;
    items: Array<{
      company_id: string;
      company_name: string;
      year: number;
      value: number;
      unit?: string | null;
      currency?: string | null;
    }>;
  }>;
  industry_distribution: Array<{
    industry: string;
    company_count: number;
    company_ids: string[];
  }>;
  risk_heatmap: Array<{
    company_id: string;
    company_name: string;
    categories: Record<string, number>;
    total: number;
  }>;
  business_overlap: Array<{
    company_id_a: string;
    company_id_b: string;
    shared_segments: string[];
    score: number;
  }>;
  warnings: string[];
};

export type FusionSummary = {
  query_intent: string;
  routes: string[];
  vector_snippet_count: number;
  metric_count: number;
  graph_path_count: number;
  highlights: string[];
  summary: string;
};

export type ResearchResponse = {
  doc_id: string;
  question: string;
  answer: string;
  grounded?: boolean;
  warnings?: string[];
  fusion_summary?: FusionSummary | null;
  query_analysis?: {
    intent: string;
    routes: string[];
    metric_keys?: string[];
    years?: number[];
  } | null;
  metrics?: MetricObservation[];
  hits?: { segment_id: string; score: number; content: string }[];
  graph_paths?: { path_id: string; summary: string; score: number }[];
  synthesis?: {
    answer: string;
    key_findings?: string[];
    confidence?: number;
    limitations?: string[];
  } | null;
  critic?: {
    passed: boolean;
    score: number;
    summary: string;
    issues?: { severity: string; message: string }[];
  } | null;
};

export type ServingEvalSummary = {
  doc_id: string;
  company_id?: string;
  segment_count?: number;
  backends?: Record<string, string>;
  l3?: { total?: number; passed?: number; pass_rate?: number };
  cases?: Array<{
    id?: string;
    question?: string;
    expect_route?: string;
    passed?: boolean;
    route_ok?: boolean;
    metric_ok?: boolean;
    semantic_ok?: boolean;
    graph_ok?: boolean;
    actual_intent?: string;
    matched_metric?: { metric_key?: string; period?: string; value?: number | string } | null;
  }>;
};

export type ScorecardSummary = {
  name: string;
  summary_scores?: Record<string, number | null>;
  serving_gate?: { allow_metric_serving?: boolean; failures?: string[] };
  retrieval_case_count?: number;
};

export const api = {
  health: () => request<{ status: string }>("/health"),
  listDocuments: () => request<DocumentRecord[]>("/api/v1/documents"),
  getDocument: (docId: string) =>
    request<DocumentRecord>(`/api/v1/documents/${encodeURIComponent(docId)}`),
  listSegments: (docId: string) =>
    request<DocumentSegment[]>(`/api/v1/documents/${encodeURIComponent(docId)}/segments`),
  getDocumentKnowledgeGraph: (docId: string) =>
    request<DocumentKnowledgeGraph>(
      `/api/v1/documents/${encodeURIComponent(docId)}/knowledge-graph`,
    ),
  listIngestionJobs: () => request<IngestionJob[]>("/api/v1/documents/jobs"),
  getIngestionMetrics: () =>
    request<IngestionQueueMetrics>("/api/v1/documents/jobs/metrics"),
  listCompanies: () => request<CompanySummary[]>("/api/v1/companies"),
  queryMetrics: (companyId: string, metricKey = "revenue") =>
    request<{ items: MetricObservation[] }>(
      `/api/v1/companies/${encodeURIComponent(companyId)}/metrics?metric_key=${encodeURIComponent(metricKey)}&limit=50`,
    ),
  metricTrend: (companyId: string, metricKey: string) =>
    request<MetricTrend>(
      `/api/v1/companies/${encodeURIComponent(companyId)}/metrics/${encodeURIComponent(metricKey)}/trend`,
    ),
  compareDocuments: (payload: {
    doc_id_a: string;
    doc_id_b: string;
    question: string;
    period?: string | null;
    metric_keys?: string[] | null;
    use_workflow: boolean;
  }) =>
    request<CompareResponse>("/api/v1/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  reportOutline: (payload: {
    doc_id: string;
    question: string;
    top_k: number;
    use_workflow: boolean;
  }) =>
    request<ReportOutlineResponse>("/api/v1/report/outline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  reportExport: (payload: {
    doc_id: string;
    question: string;
    top_k: number;
    use_workflow: boolean;
    title: string;
    format: "html" | "pdf";
  }) =>
    requestArtifact("/api/v1/report/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  reportBundleExport: (payload: {
    doc_ids: string[];
    question: string;
    top_k: number;
    report_type: "investment" | "risk";
    title: string;
    format: "html" | "pdf";
  }) =>
    requestArtifact("/api/v1/report/export-bundle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  portfolioDashboard: (companyIds: string[], metricKeys: string[]) =>
    request<PortfolioDashboard>("/api/v1/dashboard/portfolio", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_ids: companyIds, metric_keys: metricKeys }),
    }),
  research: (docId: string, question: string, topK = 5) =>
    request<ResearchResponse>("/api/v1/research/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId, question, top_k: topK }),
    }),
  researchPreview: (docId: string, question: string, topK = 5) =>
    request<ResearchResponse>("/api/v1/research/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId, question, top_k: topK }),
    }),
  listServingEvals: () => request<ServingEvalSummary[]>("/api/v1/eval/serving"),
  getServingEval: (docId: string) =>
    request<ServingEvalSummary>(`/api/v1/eval/serving/${encodeURIComponent(docId)}`),
  listScorecards: () => request<ScorecardSummary[]>("/api/v1/eval/scorecards"),
  uploadDocument: async (file: File, fields: Record<string, string>) => {
    const body = new FormData();
    body.append("file", file);
    for (const [key, value] of Object.entries(fields)) {
      if (value) body.append(key, value);
    }
    return request<DocumentRecord>("/api/v1/documents/upload", { method: "POST", body });
  },
  uploadDocumentAsync: async (file: File, fields: Record<string, string>) => {
    const body = new FormData();
    body.append("file", file);
    for (const [key, value] of Object.entries(fields)) {
      if (value) body.append(key, value);
    }
    return request<IngestionJob>("/api/v1/documents/upload/async", {
      method: "POST",
      body,
    });
  },
};
