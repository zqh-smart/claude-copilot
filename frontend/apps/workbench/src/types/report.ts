export type ReportStatus = 'draft' | 'done' | 'archived'
export type ReportType = 'earnings' | 'company' | 'industry' | 'peer' | 'event' | 'custom'
export type ReportLanguage = 'zh' | 'en'
export type ReportLength = 'brief' | 'standard' | 'long'
export type SaveState = 'idle' | 'saving' | 'saved' | 'error'
export type AIPanelTab = 'assistant' | 'citations' | 'data'
export type ReportAiCommand =
  | 'rewrite'
  | 'shorten'
  | 'expand'
  | 'explain'
  | 'find_evidence'
  | 'generate_chart'
  | 'insert_table'

export interface EditorJSONNode {
  type: string
  attrs?: Record<string, unknown>
  content?: EditorJSONNode[]
  marks?: Array<{ type: string; attrs?: Record<string, unknown> }>
  text?: string
}

export interface EditorJSON {
  type: 'doc'
  content?: EditorJSONNode[]
}

export interface ReportChartSeries {
  name: string
  type: 'bar' | 'line'
  data: number[]
  yAxisIndex?: number
}

export interface ReportChartBlock {
  id: string
  title: string
  chartType: 'bar' | 'line' | 'combo'
  xAxis: string[]
  series: ReportChartSeries[]
  dataSource?: string
}

export interface Citation {
  id: string
  reportId: string
  blockId?: string
  sourceId: string
  sourceTitle: string
  page?: number
  quote?: string
  origin?: string
}

export interface RelatedSource {
  id: string
  title: string
  origin: string
  page?: number
  date?: string
  kind?: string
}

export interface ReportVersion {
  id: string
  reportId: string
  createdAt: string
  type: 'autosave' | 'ai' | 'generate' | 'manual'
  description: string
}

export interface Report {
  id: string
  title: string
  type: ReportType
  company: string
  status: ReportStatus
  createdAt: string
  updatedAt: string
  createdBy: string
  templateId: string
  sourceIds: string[]
  content: EditorJSON
  citations: Citation[]
  relatedSources: RelatedSource[]
  versions: ReportVersion[]
  language: ReportLanguage
  length: ReportLength
  prompt: string
  backendDraftId?: string
  syncState?: 'synced' | 'cached'
}

export interface ReportListItem {
  id: string
  title: string
  type: ReportType
  status: ReportStatus
  updatedAt: string
  company: string
  createdBy: string
}

export interface CreateReportInput {
  title?: string
  type: ReportType
  company: string
  templateId: string
  sourceIds: string[]
  prompt: string
  language: ReportLanguage
  length: ReportLength
}

export interface EditorSelection {
  from: number
  to: number
  text: string
}

export interface ReportMetricRow {
  name: string
  current: string
  previous: string
  yoy: string
}

export const REPORT_TYPE_LABEL: Record<ReportType, string> = {
  earnings: '财报分析',
  company: '公司研究',
  industry: '行业研究',
  peer: '对比分析',
  event: '事件点评',
  custom: '自定义报告',
}

export const REPORT_STATUS_LABEL: Record<ReportStatus, string> = {
  draft: '草稿',
  done: '已完成',
  archived: '已归档',
}

export const PRODUCT_TEMPLATES: Array<{
  id: ReportType
  backendTemplateId: string
  name: string
  description: string
}> = [
  { id: 'earnings', backendTemplateId: 'comprehensive_financial', name: '财报分析', description: '营收、利润、现金流与风险的结构化财报解读' },
  { id: 'company', backendTemplateId: 'annual_operations', name: '公司研究', description: '经营质量、业务结构与竞争力跟踪' },
  { id: 'industry', backendTemplateId: 'financial_risk', name: '行业研究', description: '行业格局、景气度与公司定位' },
  { id: 'peer', backendTemplateId: 'period_comparison', name: '同业对比', description: '关键指标横向对比与差异拆解' },
  { id: 'event', backendTemplateId: 'profitability', name: '事件点评', description: '围绕单一事件的影响与后续跟踪' },
  { id: 'custom', backendTemplateId: 'comprehensive_financial', name: '自定义报告', description: '按重点关注自由组织章节' },
]
