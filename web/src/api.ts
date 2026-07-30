const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export type DocumentRecord = {
  doc_id: string;
  filename: string;
  status: string;
  segment_count: number;
  error_message?: string | null;
  metadata: {
    company?: string | null;
    year?: number | null;
    doc_type?: string | null;
  };
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
  listCompanies: () => request<CompanySummary[]>("/api/v1/companies"),
  queryMetrics: (companyId: string, metricKey = "revenue") =>
    request<{ items: MetricObservation[] }>(
      `/api/v1/companies/${encodeURIComponent(companyId)}/metrics?metric_key=${encodeURIComponent(metricKey)}&limit=50`,
    ),
  research: (docId: string, question: string, topK = 5) =>
    request<ResearchResponse>("/api/v1/research/query", {
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
};
