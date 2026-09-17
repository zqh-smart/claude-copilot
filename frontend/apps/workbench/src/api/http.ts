import { fastApi } from './client'

export { fastApi } from './client'

export interface DocumentSummary {
  doc_id: string
  filename: string
  status: string
  segment_count?: number
  created_at?: string | null
  error_message?: string | null
  metadata: {
    company?: string | null
    year?: number | null
    doc_type?: string | null
    industry?: string | null
  }
}

export interface DocumentSegment {
  segment_id: string
  document_id: string
  position: number
  content: string
  content_summary?: string | null
  keywords?: string[]
  metadata?: Record<string, unknown> | null
}

export interface KnowledgeGraphSummary {
  document_id: string
  nodes: Array<{ node_id: string; node_type: string; name: string }>
  relationships: Array<{
    relationship_id: string
    relationship_type: string
    source_node_id: string
    target_node_id: string
  }>
}

export interface RetrievalCase {
  id?: string
  question?: string
  expect_route?: string
  passed?: boolean
  route_ok?: boolean
  metric_ok?: boolean
  semantic_ok?: boolean
  graph_ok?: boolean
  actual_intent?: string
  matched_metric?: { metric_key?: string; period?: string; value?: number | string } | null
}

export interface ServingEvalSummary {
  doc_id: string
  document_key?: string | null
  l3?: {
    total?: number
    passed?: number
    pass_rate?: number
  }
  cases?: RetrievalCase[]
}

export interface ScorecardSummary {
  name: string
  summary_scores?: Record<string, number | null>
  serving_gate?: { allow_metric_serving?: boolean; failures?: string[] }
  retrieval_case_count?: number
}

export interface ResearchPreview {
  doc_id?: string
  question?: string
  answer: string
  grounded?: boolean
  warnings?: string[]
  fusion_summary?: {
    query_intent: string
    routes: string[]
    vector_snippet_count: number
    metric_count: number
    graph_path_count: number
    highlights: string[]
    summary: string
  } | null
  query_analysis?: { intent?: string; routes?: string[]; metric_keys?: string[]; years?: number[] }
  hits?: Array<{
    segment_id: string
    score: number
    content: string
    metadata?: Record<string, unknown>
  }>
  metrics?: MetricObservation[]
  graph_paths?: Array<{ path_id: string; summary: string; score: number }>
  synthesis?: {
    answer: string
    key_findings?: string[]
    confidence?: number
    limitations?: string[]
    citations?: Array<{ evidence_id: string; claim: string }>
  } | null
  critic?: {
    passed: boolean
    score: number
    summary: string
    issues?: Array<{ severity: string; message: string }>
  } | null
}

export interface IngestionJob {
  job_id: string
  doc_id: string
  filename: string
  status: string
  stage: string
  progress_percent: number
  attempt: number
  max_attempts: number
  created_at: string
  updated_at: string
  error_message?: string | null
}

export interface IngestionQueueMetrics {
  generated_at: string
  status_counts: Record<string, number>
  active_worker_count: number
  cancellation_requested_count: number
  oldest_ready_age_seconds?: number | null
  expired_lease_count: number
  recent_failed_count: number
  health_status: 'ok' | 'warning' | 'critical'
  alerts: Array<{
    code: string
    severity: 'warning' | 'critical'
    message: string
  }>
}

export interface CompanySummary {
  company_id: string
  name: string
  years: number[]
  document_count: number
  metric_count: number
}

export interface MetricObservation {
  company_id: string
  company: string
  document_id: string
  document_year?: number | null
  metric_key: string
  period: string
  period_year?: number | null
  value: number | string
  statement_type?: string | null
  entity_scope: 'consolidated' | 'parent_company' | 'unknown'
  unit?: string | null
  currency?: string | null
  source_table_title?: string | null
  source_section?: string | null
  page_range?: [number, number] | null
}

export interface MetricTrend {
  company: CompanySummary
  metric_key: string
  unit?: string | null
  currency?: string | null
  points: Array<{
    year: number
    period: string
    value: number
    yoy_growth?: number | null
    document_id: string
  }>
  cagr?: number | null
  warnings: string[]
}

export interface CompareResponse {
  answer_markdown: string
  matrix: Array<Record<string, unknown>>
  highlights: string[]
  warnings: string[]
  workflow: string
}

export interface PortfolioDashboard {
  company_ids: string[]
  rankings: Array<{
    metric_key: string
    items: Array<{
      company_id: string
      company_name: string
      year: number
      value: number
      unit?: string | null
      currency?: string | null
    }>
  }>
  industry_distribution: Array<{
    industry: string
    company_count: number
    company_ids: string[]
  }>
  risk_heatmap: Array<{
    company_id: string
    company_name: string
    categories: Record<string, number>
    total: number
  }>
  business_overlap: Array<{
    company_id_a: string
    company_id_b: string
    shared_segments: string[]
    score: number
  }>
  warnings: string[]
}

export type ReportTemplateId =
  | 'comprehensive_financial'
  | 'annual_operations'
  | 'profitability'
  | 'cash_and_solvency'
  | 'financial_risk'
  | 'period_comparison'
export type ReportLanguage = 'zh' | 'en'
export type ReportLength = 'standard' | 'brief' | 'long'
export type DraftStatus = 'draft' | 'revised' | 'final'

export interface ReportTemplate {
  template_id: ReportTemplateId
  name: string
  category: string
  description: string
  scenario?: string
  chapters: Array<{
    chapter_id: string
    title: string
    hints: string[]
    required_metrics: string[]
    section_hints: string[]
    analysis_requirements: string[]
    must_cite: boolean
  }>
}

export interface ReportCitation {
  citation_id: string
  doc_id: string
  filename: string
  section_title?: string | null
  page?: number | null
  excerpt: string
  path_label: string
  metric_key?: string | null
}

export interface ReportDraftSection {
  section_id: string
  chapter_id: string
  title: string
  content: string
  citation_ids: string[]
  required_metrics: string[]
  analysis_requirements: string[]
}

export interface ReportDraft {
  draft_id: string
  title: string
  template_id: ReportTemplateId
  language: ReportLanguage
  length: ReportLength
  prompt: string
  status: DraftStatus
  sources: Array<{
    doc_id: string
    filename: string
    company?: string | null
    year?: number | null
    doc_type?: string | null
  }>
  sections: ReportDraftSection[]
  citations: ReportCitation[]
  warnings: string[]
  created_at: string
  updated_at: string
}

export interface ReportDraftSummary {
  draft_id: string
  title: string
  template_id: ReportTemplateId
  status: DraftStatus
  source_count: number
  updated_at: string
}

export interface AssistReportDraftResponse {
  section_id: string
  suggested_content: string
  applied: boolean
  draft?: ReportDraft | null
}

export type ChatMemoryLayer = 'L0' | 'L1' | 'L2' | 'L3'

export interface ChatMemoryHealth {
  status: string
  enabled?: boolean
  base_url?: string
  reason?: string
  error?: string
}

export interface ChatMemoryLayerResponse {
  layer?: ChatMemoryLayer
  items: Array<Record<string, unknown>>
  total?: number
  limit?: number
  offset?: number
}

export async function listDocuments(): Promise<DocumentSummary[]> {
  const response = await fastApi.get<DocumentSummary[]>('/api/v1/documents')
  return response.data
}

export async function listServingEvals(): Promise<ServingEvalSummary[]> {
  const response = await fastApi.get<ServingEvalSummary[]>('/api/v1/eval/serving')
  return response.data
}

export async function getServingEval(docId: string): Promise<ServingEvalSummary> {
  const response = await fastApi.get<ServingEvalSummary>(
    `/api/v1/eval/serving/${encodeURIComponent(docId)}`,
  )
  return response.data
}

export async function listScorecards(): Promise<ScorecardSummary[]> {
  const response = await fastApi.get<ScorecardSummary[]>('/api/v1/eval/scorecards')
  return response.data
}

export async function listSegments(docId: string): Promise<DocumentSegment[]> {
  const response = await fastApi.get<DocumentSegment[]>(
    `/api/v1/documents/${encodeURIComponent(docId)}/segments`,
  )
  return response.data
}

export async function getKnowledgeGraph(docId: string): Promise<KnowledgeGraphSummary> {
  const response = await fastApi.get<KnowledgeGraphSummary>(
    `/api/v1/documents/${encodeURIComponent(docId)}/knowledge-graph`,
  )
  return response.data
}

export async function previewResearch(
  docId: string,
  question: string,
  topK = 5,
): Promise<ResearchPreview> {
  const response = await fastApi.post<ResearchPreview>('/api/v1/research/preview', {
    doc_id: docId,
    question,
    top_k: topK,
  })
  return response.data
}

export async function researchDocument(
  docId: string,
  question: string,
  topK = 5,
): Promise<ResearchPreview> {
  const response = await fastApi.post<ResearchPreview>(
    '/api/v1/research/query',
    { doc_id: docId, question, top_k: topK },
    { timeout: 180_000 },
  )
  return response.data
}

export async function uploadDocumentAsync(
  file: File,
  fields: Record<string, string>,
): Promise<IngestionJob> {
  const body = new FormData()
  body.append('file', file)
  Object.entries(fields).forEach(([key, value]) => {
    if (value) body.append(key, value)
  })
  const response = await fastApi.post<IngestionJob>('/api/v1/documents/upload/async', body, {
    timeout: 120_000,
  })
  return response.data
}

export async function listIngestionJobs(): Promise<IngestionJob[]> {
  const response = await fastApi.get<IngestionJob[]>('/api/v1/documents/jobs')
  return response.data
}

export async function getIngestionMetrics(): Promise<IngestionQueueMetrics> {
  const response = await fastApi.get<IngestionQueueMetrics>('/api/v1/documents/jobs/metrics')
  return response.data
}

export async function retryIngestionJob(jobId: string): Promise<IngestionJob> {
  const response = await fastApi.post<IngestionJob>(
    `/api/v1/documents/jobs/${encodeURIComponent(jobId)}/retry`,
  )
  return response.data
}

export async function cancelIngestionJob(jobId: string): Promise<IngestionJob> {
  const response = await fastApi.post<IngestionJob>(
    `/api/v1/documents/jobs/${encodeURIComponent(jobId)}/cancel`,
  )
  return response.data
}

export async function listCompanies(): Promise<CompanySummary[]> {
  const response = await fastApi.get<CompanySummary[]>('/api/v1/companies')
  return response.data
}

export async function queryMetrics(
  companyId: string,
  metricKey: string,
): Promise<MetricObservation[]> {
  const response = await fastApi.get<{ items: MetricObservation[] }>(
    `/api/v1/companies/${encodeURIComponent(companyId)}/metrics`,
    { params: { metric_key: metricKey, limit: 50 } },
  )
  return response.data.items
}

export async function getMetricTrend(
  companyId: string,
  metricKey: string,
): Promise<MetricTrend> {
  const response = await fastApi.get<MetricTrend>(
    `/api/v1/companies/${encodeURIComponent(companyId)}/metrics/${encodeURIComponent(metricKey)}/trend`,
  )
  return response.data
}

export async function compareDocuments(payload: {
  doc_id_a: string
  doc_id_b: string
  question: string
  period?: string | null
  metric_keys?: string[] | null
  use_workflow: boolean
}): Promise<CompareResponse> {
  const response = await fastApi.post<CompareResponse>('/api/v1/compare', payload, {
    timeout: 120_000,
  })
  return response.data
}

export async function getPortfolioDashboard(
  companyIds: string[],
  metricKeys: string[],
): Promise<PortfolioDashboard> {
  const response = await fastApi.post<PortfolioDashboard>('/api/v1/dashboard/portfolio', {
    company_ids: companyIds,
    metric_keys: metricKeys,
  })
  return response.data
}

export async function listReportTemplates(): Promise<ReportTemplate[]> {
  const response = await fastApi.get<ReportTemplate[]>('/api/v1/report/templates')
  return response.data
}

export async function listReportDrafts(): Promise<ReportDraftSummary[]> {
  const response = await fastApi.get<ReportDraftSummary[]>('/api/v1/report/drafts')
  return response.data
}

export async function createReportDraft(payload: {
  doc_ids: string[]
  template_id: ReportTemplateId
  prompt?: string
  language?: ReportLanguage
  length?: ReportLength
  title?: string
  top_k?: number
}): Promise<ReportDraft> {
  const response = await fastApi.post<ReportDraft>('/api/v1/report/drafts', payload, {
    timeout: 300_000,
  })
  return response.data
}

export async function getReportDraft(draftId: string): Promise<ReportDraft> {
  const response = await fastApi.get<ReportDraft>(
    `/api/v1/report/drafts/${encodeURIComponent(draftId)}`,
  )
  return response.data
}

export async function patchReportDraft(
  draftId: string,
  payload: { title?: string; status?: DraftStatus; sections?: ReportDraftSection[] },
): Promise<ReportDraft> {
  const response = await fastApi.patch<ReportDraft>(
    `/api/v1/report/drafts/${encodeURIComponent(draftId)}`,
    payload,
  )
  return response.data
}

export async function assistReportDraft(
  draftId: string,
  payload: { section_id: string; instruction: string; apply?: boolean },
): Promise<AssistReportDraftResponse> {
  const response = await fastApi.post<AssistReportDraftResponse>(
    `/api/v1/report/drafts/${encodeURIComponent(draftId)}/assist`,
    payload,
    { timeout: 180_000 },
  )
  return response.data
}

export async function exportReportDraft(
  draftId: string,
  format: 'html' | 'pdf',
  title: string,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fastApi.post<Blob>(
    `/api/v1/report/drafts/${encodeURIComponent(draftId)}/export`,
    { format, title },
    { responseType: 'blob', timeout: 180_000 },
  )
  const disposition = String(response.headers['content-disposition'] || '')
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const filename = encodedName
    ? decodeURIComponent(encodedName)
    : disposition.match(/filename="?([^";]+)"?/i)?.[1] || `${title}.${format}`
  return { blob: response.data, filename }
}

export async function getChatMemoryHealth(): Promise<ChatMemoryHealth> {
  const response = await fastApi.get<ChatMemoryHealth>('/api/v1/chat-memory/health')
  return response.data
}

export async function getChatMemoryLayer(
  layer: ChatMemoryLayer,
  options: { sessionId?: string; limit?: number; offset?: number } = {},
): Promise<ChatMemoryLayerResponse> {
  const response = await fastApi.get<ChatMemoryLayerResponse>(
    `/api/v1/chat-memory/layers/${layer}`,
    {
      params: {
        session_id: options.sessionId || undefined,
        limit: options.limit ?? 40,
        offset: options.offset ?? 0,
      },
    },
  )
  return response.data
}

export async function searchChatMemory(
  query: string,
  sessionId?: string,
): Promise<ChatMemoryLayerResponse> {
  const response = await fastApi.get<ChatMemoryLayerResponse>('/api/v1/chat-memory/search', {
    params: { q: query, session_id: sessionId || undefined, limit: 30 },
  })
  return response.data
}
