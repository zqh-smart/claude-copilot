/**
 * Parse the Agent Launch Context passed by the workbench via URL query params.
 *
 * Contract (kept in sync with packages/contracts AgentLaunchContext):
 *   cc_source   - 'knowledge' | 'metrics' | 'reports' | 'research'
 *   cc_resource - opaque resource id (doc id, company id, ...)
 *   cc_prompt   - optional pre-filled user prompt (kept short)
 *
 * Anything else (document text, secrets, trace ids) must NOT travel in the URL.
 */
import type { AgentLaunchContext, AgentLaunchSource } from '@claude-copilot/contracts'

const SOURCES: readonly AgentLaunchSource[] = [
  'knowledge',
  'metrics',
  'reports',
  'research',
] as const

export function readLaunchContext(search: string): AgentLaunchContext | undefined {
  const params = new URLSearchParams(search)
  const source = params.get('cc_source')
  const resourceId = params.get('cc_resource')
  const prompt = params.get('cc_prompt')

  if (!source || !resourceId) return undefined
  if (!SOURCES.includes(source as AgentLaunchSource)) return undefined

  return {
    source: source as AgentLaunchSource,
    resourceId,
    prompt: prompt ?? undefined,
  }
}

export function summarizeLaunchContext(context: AgentLaunchContext | undefined): string {
  if (!context) return '自由对话'
  const sourceLabel: Record<AgentLaunchSource, string> = {
    knowledge: '知识库',
    metrics: '指标中心',
    reports: '报告中心',
    research: '研究问答',
  }
  return `${sourceLabel[context.source]} · ${context.resourceId.slice(0, 8)}…`
}