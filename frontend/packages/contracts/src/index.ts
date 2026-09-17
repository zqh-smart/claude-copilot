export type AgentLaunchSource = 'knowledge' | 'metrics' | 'reports' | 'research'

export interface DocumentContext {
  documentId: string
  title: string
  selectedChunkIds?: string[]
}

export interface MetricContext {
  metricId: string
  companyId: string
  period?: string
}

export interface ResearchContext {
  taskId: string
  companyId?: string
  documentIds?: string[]
}

export interface AgentLaunchContext {
  source: AgentLaunchSource
  resourceId: string
  prompt?: string
}

export interface PublicRuntimeConfig {
  apiBaseUrl: string
  chatUrl: string
  assistantId?: string
}
