import {
  createReportDraft,
  getReportDraft,
  listReportDrafts,
  patchReportDraft,
  type DraftStatus,
  type ReportDraft,
  type ReportDraftSummary,
  type ReportTemplateId,
} from '@/api/http'
import { contentToSectionPayload, draftSectionsToDocument } from '@/services/reportDocument'
import type { CreateReportInput, Report, ReportListItem, ReportStatus, ReportType } from '@/types/report'

const STORAGE_KEY = 'cc:report-workspace'
const LAST_OPENED_KEY = 'cc:report-last-opened'
const CURRENT_USER = 'me'

export interface ReportRepository {
  listReports(): Promise<ReportListItem[]>
  getReport(id: string): Promise<Report | null>
  createReport(input: CreateReportInput): Promise<Report>
  updateReport(id: string, patch: Partial<Report>, versionHint?: { type: Report['versions'][number]['type']; description: string }): Promise<Report>
  deleteReport(id: string): Promise<void>
  getLastOpenedId(): string | null
  setLastOpenedId(id: string): void
}

interface WorkspaceSnapshot {
  reports: Report[]
}

function readSnapshot(): WorkspaceSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as WorkspaceSnapshot
    return Array.isArray(parsed.reports) ? parsed : null
  } catch {
    return null
  }
}

function writeSnapshot(reports: Report[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ reports }))
}

function mapDraftStatus(status: DraftStatus): ReportStatus {
  return status === 'final' ? 'done' : 'draft'
}

function mapTemplateType(templateId: string): ReportType {
  if (templateId === 'annual_operations') return 'company'
  if (templateId === 'financial_risk') return 'industry'
  if (templateId === 'period_comparison') return 'peer'
  if (templateId === 'profitability') return 'event'
  return 'earnings'
}

function draftToReport(draft: ReportDraft, existing?: Report): Report {
  return {
    id: draft.draft_id,
    title: draft.title,
    type: existing?.type || mapTemplateType(draft.template_id),
    company: draft.sources.find((item) => item.company)?.company || existing?.company || '',
    status: mapDraftStatus(draft.status),
    createdAt: draft.created_at,
    updatedAt: draft.updated_at,
    createdBy: existing?.createdBy || CURRENT_USER,
    templateId: draft.template_id,
    sourceIds: draft.sources.map((item) => item.doc_id),
    content: draftSectionsToDocument(draft.title, draft.sections),
    citations: draft.citations.map((item) => ({
      id: item.citation_id,
      reportId: draft.draft_id,
      sourceId: item.doc_id,
      sourceTitle: item.filename,
      page: item.page ?? undefined,
      quote: item.excerpt,
      origin: item.path_label,
    })),
    relatedSources: draft.sources.map((item) => ({
      id: item.doc_id,
      title: item.filename,
      origin: item.doc_type || '知识库材料',
    })),
    versions: existing?.versions || [],
    language: draft.language,
    length: draft.length,
    prompt: draft.prompt,
    backendDraftId: draft.draft_id,
    syncState: 'synced',
  }
}

function summaryToReport(summary: ReportDraftSummary, cached?: Report): Report {
  return {
    id: summary.draft_id,
    title: summary.title,
    type: cached?.type || mapTemplateType(summary.template_id),
    company: cached?.company || '',
    status: mapDraftStatus(summary.status),
    createdAt: cached?.createdAt || summary.updated_at,
    updatedAt: summary.updated_at,
    createdBy: cached?.createdBy || CURRENT_USER,
    templateId: summary.template_id,
    sourceIds: cached?.sourceIds || [],
    content: cached?.content || {
      type: 'doc',
      content: [{ type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: summary.title }] }],
    },
    citations: cached?.citations || [],
    relatedSources: cached?.relatedSources || [],
    versions: cached?.versions || [],
    language: cached?.language || 'zh',
    length: cached?.length || 'standard',
    prompt: cached?.prompt || '',
    backendDraftId: summary.draft_id,
    syncState: cached ? 'cached' : 'synced',
  }
}

function toListItem(report: Report): ReportListItem {
  return {
    id: report.id,
    title: report.title,
    type: report.type,
    status: report.status,
    updatedAt: report.updatedAt,
    company: report.company,
    createdBy: report.createdBy,
  }
}

class RemoteReportRepository implements ReportRepository {
  private reports: Report[] = []
  private ready: Promise<void>

  constructor() {
    this.ready = this.hydrate()
  }

  private async hydrate() {
    const cached = readSnapshot()?.reports || []
    try {
      const remote = await listReportDrafts()
      this.reports = remote.map((summary) => {
        const existing = cached.find((item) => item.backendDraftId === summary.draft_id || item.id === summary.draft_id)
        return summaryToReport(summary, existing)
      })
      this.persist()
    } catch {
      this.reports = cached
        .filter((item) => item.backendDraftId)
        .map((item) => ({ ...item, syncState: 'cached' as const }))
    }
  }

  private persist() {
    writeSnapshot(this.reports)
  }

  private replace(next: Report) {
    const exists = this.reports.some((item) => item.id === next.id)
    this.reports = exists
      ? this.reports.map((item) => (item.id === next.id ? next : item))
      : [next, ...this.reports]
    this.persist()
    return next
  }

  async listReports() {
    await this.ready
    return this.reports
      .slice()
      .sort((a, b) => +new Date(b.updatedAt) - +new Date(a.updatedAt))
      .map(toListItem)
  }

  async getReport(id: string) {
    await this.ready
    const cached = this.reports.find((item) => item.id === id || item.backendDraftId === id)
    const draftId = cached?.backendDraftId || id
    try {
      const draft = await getReportDraft(draftId)
      return this.replace(draftToReport(draft, cached))
    } catch (reason) {
      if (cached) return this.replace({ ...cached, syncState: 'cached' })
      throw reason
    }
  }

  async createReport(input: CreateReportInput) {
    await this.ready
    if (!input.sourceIds.length) {
      throw new Error('请至少选择一份已完成解析的研究材料')
    }
    const title = input.title?.trim() || `${input.company || '未命名对象'}报告框架`
    const draft = await createReportDraft({
      doc_ids: input.sourceIds,
      template_id: input.templateId as ReportTemplateId,
      prompt: input.prompt,
      language: input.language,
      length: input.length,
      title,
    })
    const created = this.replace(draftToReport(draft, {
      id: draft.draft_id,
      title,
      type: input.type,
      company: input.company,
      status: 'draft',
      createdAt: draft.created_at,
      updatedAt: draft.updated_at,
      createdBy: CURRENT_USER,
      templateId: input.templateId,
      sourceIds: input.sourceIds,
      content: { type: 'doc' },
      citations: [],
      relatedSources: [],
      versions: [],
      language: input.language,
      length: input.length,
      prompt: input.prompt,
      backendDraftId: draft.draft_id,
    }))
    this.setLastOpenedId(created.id)
    return created
  }

  async updateReport(
    id: string,
    patch: Partial<Report>,
    _versionHint?: { type: Report['versions'][number]['type']; description: string },
  ) {
    await this.ready
    const current = this.reports.find((item) => item.id === id)
    if (!current?.backendDraftId) throw new Error('报告尚未同步到后端，无法保存')
    const candidate = { ...current, ...patch, id }
    const draft = await patchReportDraft(current.backendDraftId, {
      title: candidate.title,
      status: candidate.status === 'done' ? 'final' : 'revised',
      sections: contentToSectionPayload(candidate.content),
    })
    return this.replace(draftToReport(draft, candidate))
  }

  async deleteReport(_id: string) {
    throw new Error('后端删除接口尚未开放')
  }

  getLastOpenedId() {
    return localStorage.getItem(LAST_OPENED_KEY)
  }

  setLastOpenedId(id: string) {
    localStorage.setItem(LAST_OPENED_KEY, id)
  }
}

/** FastAPI ReportDraft is canonical; localStorage is a read-only offline cache. */
export const reportRepository: ReportRepository = new RemoteReportRepository()
