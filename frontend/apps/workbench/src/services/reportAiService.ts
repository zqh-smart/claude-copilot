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

export async function runReportAiCommand(request: AiCommandRequest): Promise<AiCommandResult> {
  if (request.command === 'find_evidence') {
    return { command: request.command, message: '已切换到引用与来源。', openCitations: true }
  }
  return {
    command: request.command,
    message: 'AI 编辑尚未接入后端证据辅助接口，本次不会修改报告正文。',
  }
}

export async function askReportAssistant(_question: string, _selection: EditorSelection | null): Promise<string> {
  return 'AI 研究助手将在下一阶段接入后端 /assist 接口；当前不会生成或改写任何正文。'
}
