import {
  createReportDraft,
  getReportDraft,
  listReportDrafts,
  patchReportDraft,
  type DraftStatus,
  type ReportDraft,
} from '@/api/http'
import { contentToSectionPayload, defaultChapters, skeletonDocument } from '@/services/reportDocument'
import { MOCK_CURRENT_USER, seedReports } from '@/services/reportMock'
import type { CreateReportInput, EditorJSON, Report, ReportListItem, ReportStatus } from '@/types/report'

const STORAGE_KEY = 'cc:report-workspace'
const LAST_OPENED_KEY = 'cc:report-last-opened'
const VERSION_CAP = 20

export interface ReportRepository {
  listReports(): Promise<ReportListItem[]>
  getReport(id: string): Promise<Report | null>
  createReport(input: CreateReportInput): Promise<Report>
  updateReport(id: string, patch: Partial<Report>, versionHint?: { type: Report['versions'][number]['type']; description: string }): Promise<Report>
  deleteReport(id: string): Promise<void>
  generateReport(id: string, onProgress?: (report: Report) => void): Promise<Report>
  getLastOpenedId(): string | null
  setLastOpenedId(id: string): void
}

interface WorkspaceSnapshot {
  reports: Report[]
}

function nowIso() {
  return new Date().toISOString()
}

function uid(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`
}

function readSnapshot(): WorkspaceSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as WorkspaceSnapshot
    if (!Array.isArray(parsed.reports)) return null
    return parsed
  } catch {
    return null
  }
}

function writeSnapshot(reports: Report[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ reports }))
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

function mapDraftStatus(status: DraftStatus): ReportStatus {
  if (status === 'final') return 'done'
  return 'draft'
}

function draftToReport(draft: ReportDraft, existing?: Report): Report {
  const sections: EditorJSON = {
    type: 'doc',
    content: [
      { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: draft.title }] },
      ...draft.sections.flatMap((section) => [
        { type: 'heading' as const, attrs: { level: 2 }, content: [{ type: 'text', text: section.title }] },
        { type: 'paragraph' as const, content: section.content ? [{ type: 'text', text: section.content }] : [] },
      ]),
    ],
  }
  return {
    id: existing?.id || draft.draft_id,
    title: draft.title,
    type: existing?.type || 'earnings',
    company: existing?.company || draft.sources[0]?.company || '',
    status: mapDraftStatus(draft.status),
    createdAt: draft.created_at,
    updatedAt: draft.updated_at,
    createdBy: existing?.createdBy || MOCK_CURRENT_USER,
    templateId: existing?.templateId || draft.template_id,
    sourceIds: draft.sources.map((item) => item.doc_id),
    content: existing?.content?.content?.length ? existing.content : sections,
    citations: existing?.citations?.length
      ? existing.citations
      : draft.citations.map((item) => ({
          id: item.citation_id,
          reportId: draft.draft_id,
          sourceId: item.doc_id,
          sourceTitle: item.filename,
          page: item.page ?? undefined,
          quote: item.excerpt,
          origin: item.path_label,
        })),
    relatedSources:
      existing?.relatedSources?.length
        ? existing.relatedSources
        : draft.sources.map((item) => ({
            id: item.doc_id,
            title: item.filename,
            origin: item.doc_type || '知识库材料',
          })),
    versions: existing?.versions?.length
      ? existing.versions
      : [{ id: uid('v'), reportId: draft.draft_id, createdAt: draft.updated_at, type: 'generate', description: '初始生成' }],
    language: draft.language,
    length: draft.length,
    prompt: draft.prompt,
    backendDraftId: draft.draft_id,
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

class LocalHybridReportRepository implements ReportRepository {
  private reports: Report[] = []
  private ready: Promise<void>

  constructor() {
    this.ready = this.hydrate()
  }

  private async hydrate() {
    const local = readSnapshot()
    this.reports = local?.reports?.length ? local.reports : seedReports()
    if (!local?.reports?.length) writeSnapshot(this.reports)
    try {
      const remote = await listReportDrafts()
      for (const summary of remote) {
        if (this.reports.some((item) => item.backendDraftId === summary.draft_id || item.id === summary.draft_id)) {
          continue
        }
        this.reports.push({
          id: summary.draft_id,
          title: summary.title,
          type: 'custom',
          company: '',
          status: mapDraftStatus(summary.status),
          createdAt: summary.updated_at,
          updatedAt: summary.updated_at,
          createdBy: MOCK_CURRENT_USER,
          templateId: summary.template_id,
          sourceIds: [],
          content: skeletonDocument(summary.title, ['正文']),
          citations: [],
          relatedSources: [],
          versions: [],
          language: 'zh',
          length: 'standard',
          prompt: '',
          backendDraftId: summary.draft_id,
        })
      }
      writeSnapshot(this.reports)
    } catch {
      // TODO: backend listReportDrafts unavailable — keep local/mock workspace.
    }
  }

  private persist() {
    writeSnapshot(this.reports)
  }

  private replace(next: Report) {
    this.reports = this.reports.map((item) => (item.id === next.id ? next : item))
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
    const local = this.reports.find((item) => item.id === id)
    if (!local) return null
    if (local.backendDraftId && !(local.content.content || []).some((node) => node.type === 'heading' && node.attrs?.level === 1)) {
      try {
        const draft = await getReportDraft(local.backendDraftId)
        return this.replace(draftToReport(draft, local))
      } catch {
        // TODO: getReportDraft failed; serve local editor JSON.
      }
    }
    return local
  }

  async createReport(input: CreateReportInput) {
    await this.ready
    const id = uid('rpt')
    const title = input.title?.trim() || `${input.company || '未命名对象'}${input.type === 'earnings' ? '财报分析' : '研究报告'}`
    const chapters = defaultChapters(input.type)
    const created: Report = {
      id,
      title,
      type: input.type,
      company: input.company,
      status: 'generating',
      createdAt: nowIso(),
      updatedAt: nowIso(),
      createdBy: MOCK_CURRENT_USER,
      templateId: input.templateId,
      sourceIds: input.sourceIds,
      content: skeletonDocument(title, chapters),
      citations: [],
      relatedSources: [],
      versions: [{ id: uid('v'), reportId: id, createdAt: nowIso(), type: 'generate', description: '创建报告' }],
      language: input.language,
      length: input.length,
      prompt: input.prompt,
      generatingChapters: chapters.map((title, index) => ({
        title,
        status: index === 0 ? 'running' : 'pending',
      })),
    }
    this.reports.unshift(created)
    this.persist()
    this.setLastOpenedId(id)

    if (input.sourceIds.length) {
      try {
        const draft = await createReportDraft({
          doc_ids: input.sourceIds,
          template_id: input.templateId as ReportDraft['template_id'],
          prompt: input.prompt,
          language: input.language,
          length: input.length,
          title,
        })
        const merged = draftToReport(draft, { ...created, status: 'draft', generatingChapters: [] })
        return this.replace(merged)
      } catch {
        // TODO: createReportDraft unavailable — continue with local generating document.
      }
    }
    return created
  }

  async updateReport(id: string, patch: Partial<Report>, versionHint?: { type: Report['versions'][number]['type']; description: string }) {
    await this.ready
    const current = this.reports.find((item) => item.id === id)
    if (!current) throw new Error('报告不存在')
    const versions = versionHint
      ? [
          { id: uid('v'), reportId: id, createdAt: nowIso(), type: versionHint.type, description: versionHint.description },
          ...current.versions,
        ].slice(0, VERSION_CAP)
      : current.versions
    const next: Report = {
      ...current,
      ...patch,
      id,
      updatedAt: nowIso(),
      versions,
    }
    this.replace(next)
    if (next.backendDraftId) {
      try {
        const sections = contentToSectionPayload(next.content).map((section, index) => ({
          section_id: `local-${index + 1}`,
          chapter_id: `local-${index + 1}`,
          title: section.title,
          content: section.content,
          citation_ids: [] as string[],
          required_metrics: [] as string[],
          analysis_requirements: [] as string[],
        }))
        await patchReportDraft(next.backendDraftId, {
          title: next.title,
          status: next.status === 'done' ? 'final' : 'draft',
          sections,
        })
      } catch {
        // TODO: patchReportDraft failed; local editor JSON remains source of truth.
      }
    }
    return next
  }

  async deleteReport(id: string) {
    await this.ready
    this.reports = this.reports.filter((item) => item.id !== id)
    this.persist()
  }

  async generateReport(id: string, onProgress?: (report: Report) => void) {
    await this.ready
    const current = this.reports.find((item) => item.id === id)
    if (!current) throw new Error('报告不存在')
    if (current.backendDraftId) return current
    const chapters = current.generatingChapters?.length
      ? current.generatingChapters
      : defaultChapters(current.type).map((title) => ({ title, status: 'pending' as const }))

    let cursor = { ...current, generatingChapters: chapters, status: 'generating' as const }
    this.replace(cursor)
    onProgress?.(cursor)

    for (let index = 0; index < chapters.length; index += 1) {
      cursor = {
        ...cursor,
        generatingChapters: chapters.map((item, i) => ({
          ...item,
          status: i < index ? 'done' : i === index ? 'running' : 'pending',
        })),
        updatedAt: nowIso(),
      }
      this.replace(cursor)
      onProgress?.(cursor)
      await sleep(450)
    }

    const { catlH1Document } = await import('@/services/reportDocument')
    const finished: Report = {
      ...cursor,
      status: 'draft',
      generatingChapters: chapters.map((item) => ({ ...item, status: 'done' })),
      content: current.company.includes('宁德') ? catlH1Document() : cursor.content,
      updatedAt: nowIso(),
      versions: [
        { id: uid('v'), reportId: id, createdAt: nowIso(), type: 'generate' as const, description: '初始生成' },
        ...cursor.versions,
      ].slice(0, VERSION_CAP),
    }
    return this.replace(finished)
  }

  getLastOpenedId() {
    return localStorage.getItem(LAST_OPENED_KEY)
  }

  setLastOpenedId(id: string) {
    localStorage.setItem(LAST_OPENED_KEY, id)
  }
}

/** Adapter: local editor JSON is canonical; FastAPI drafts are optional sync. */
export const reportRepository: ReportRepository = new LocalHybridReportRepository()

/** Reserved for future token streaming. Today generateReport() fills chapters. */
export async function streamReport(
  id: string,
  onProgress?: (report: Report) => void,
): Promise<Report> {
  // TODO: replace with backend streamReport() when the API exists.
  return reportRepository.generateReport(id, onProgress)
}
