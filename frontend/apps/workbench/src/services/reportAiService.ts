import type { EditorSelection, ReportAiCommand } from '@/types/report'

export interface AiCommandRequest {
  command: ReportAiCommand
  selection: EditorSelection | null
  instruction?: string
}

export interface AiCommandResult {
  command: ReportAiCommand
  message: string
  replacement?: string
  insertChart?: boolean
  insertTable?: boolean
  openCitations?: boolean
}

const MOCK_REPLIES: Record<ReportAiCommand, string> = {
  rewrite: '已按研报表述改写选中段落，请在正文中确认数字与引用是否仍成立。',
  shorten: '已压缩选中内容，保留关键结论与同比变化。',
  expand: '已补充分析性表述。后端证据检索尚未接通时，请人工核对来源。',
  explain: '这段主要在说明盈利仍有韧性，但毛利率走弱需要原材料与产品结构两侧验证。',
  find_evidence: '已切换到引用与来源。请核对 citation 与原文页码。',
  generate_chart: '已准备插入营收趋势图 block。',
  insert_table: '已准备插入财务指标表。',
}

export async function runReportAiCommand(request: AiCommandRequest): Promise<AiCommandResult> {
  // TODO: wire assistReportDraft / a dedicated command API. Local adapter only.
  const text = request.selection?.text.trim() || ''
  if (request.command === 'rewrite' && text) {
    return { command: request.command, message: MOCK_REPLIES.rewrite, replacement: `${text.replace(/。/g, '；')}整体判断维持不变。` }
  }
  if (request.command === 'shorten' && text) {
    const clipped = text.slice(0, Math.max(24, Math.floor(text.length * 0.55)))
    return { command: request.command, message: MOCK_REPLIES.shorten, replacement: clipped.endsWith('。') ? clipped : `${clipped}。` }
  }
  if (request.command === 'expand' && text) {
    return {
      command: request.command,
      message: MOCK_REPLIES.expand,
      replacement: `${text}${text.endsWith('。') ? '' : '。'}从结构上看，量增仍是主贡献，价格与成本需在后续章节展开。`,
    }
  }
  if (request.command === 'find_evidence') {
    return { command: request.command, message: MOCK_REPLIES.find_evidence, openCitations: true }
  }
  if (request.command === 'generate_chart') {
    return { command: request.command, message: MOCK_REPLIES.generate_chart, insertChart: true }
  }
  if (request.command === 'insert_table') {
    return { command: request.command, message: MOCK_REPLIES.insert_table, insertTable: true }
  }
  return { command: request.command, message: request.instruction?.trim() || MOCK_REPLIES[request.command] }
}

export async function askReportAssistant(question: string, selection: EditorSelection | null): Promise<string> {
  // TODO: replace with streaming assistant endpoint bound to the open report.
  const selected = selection?.text.trim()
  if (selected) {
    return `针对选中的「${selected.slice(0, 42)}${selected.length > 42 ? '…' : ''}」：${question}\n\n当前是本地助手适配层，不会编造未引用的新数据。可以把这段改写、扩写，或切到「引用与来源」核对证据。`
  }
  return `${question}\n\n我可以改写、扩写、插入财务表或趋势图。完整证据检索需要后端 streamReport / assist 接口接通。`
}
