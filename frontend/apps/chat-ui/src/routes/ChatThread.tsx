import {
  ActionBarPrimitive,
  AuiIf,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  type SourceMessagePartProps,
} from '@assistant-ui/react'
import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown'
import type { AgentLaunchContext } from '@claude-copilot/contracts'
import {
  ArrowDown,
  BarChart3,
  BookOpenText,
  Building2,
  Copy,
  FileSearch,
  Sparkles,
} from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { ResearchComposer } from '@/components/ResearchComposer'
import { SourcesDrawer, type ResearchSource } from '@/components/SourcesDrawer'
import { subscribeLangGraphError } from '@/runtime/connection'
import { langGraphClient } from '@/runtime/langgraph'

/**
 * The chat surface.
 *
 * Built from assistant-ui primitives only — this file owns markup and nothing
 * else. Streaming, thread persistence, interrupts and cancellation all live in
 * the runtime wired up in `@/App`. Tool UI / Generative UI / citations will
 * attach here later (via `MessagePrimitive.Parts` `components.tools`) without
 * changing the surrounding layout.
 */
export function ChatThread({ launchContext }: { launchContext?: AgentLaunchContext }) {
  return (
    <ThreadPrimitive.Root className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-3 pb-5 pt-4 sm:px-6 sm:pt-6">
        <AuiIf condition={(s) => s.thread.isEmpty}>
          <div className="mx-auto flex min-h-[430px] max-w-[820px] flex-col items-center justify-center pb-6 text-center">
            <div className="mb-4 grid size-12 place-items-center rounded-2xl bg-accent text-primary">
              <BarChart3 className="size-6" />
            </div>
            <h1 className="text-xl font-semibold tracking-[-0.02em]">金融研究 Agent</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              基于财报、公告、研报与知识库进行研究分析
            </p>
            <div className="mt-8 grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
              {suggestions.map(({ title, description, prompt, icon: Icon }) => (
                <ThreadPrimitive.Suggestion
                  key={title}
                  prompt={prompt}
                  send
                  className="group min-h-[108px] rounded-2xl border border-border bg-card p-4 text-left transition-all duration-150 hover:-translate-y-0.5 hover:border-primary/25 hover:bg-accent/30"
                >
                  <span className="mb-3 grid size-8 place-items-center rounded-xl bg-muted text-primary transition-colors group-hover:bg-accent">
                    <Icon className="size-4" />
                  </span>
                  <span className="block text-sm font-semibold">{title}</span>
                  <span className="mt-1 block whitespace-pre-line text-xs leading-5 text-muted-foreground">
                    {description}
                  </span>
                </ThreadPrimitive.Suggestion>
              ))}
            </div>
          </div>
        </AuiIf>
        <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
      </ThreadPrimitive.Viewport>

      <ConnectionAlert />
      <AuiIf condition={(state) => !state.thread.isEmpty}>
        <ThreadPrimitive.ScrollToBottom asChild>
          <button
            type="button"
            className="absolute bottom-[146px] left-1/2 z-20 grid size-9 -translate-x-1/2 place-items-center rounded-full border border-border bg-card text-muted-foreground shadow-sm transition-colors hover:text-primary disabled:hidden"
            aria-label="回到底部"
          >
            <ArrowDown className="size-4" />
          </button>
        </ThreadPrimitive.ScrollToBottom>
      </AuiIf>
      <ResearchComposer launchContext={launchContext} />
    </ThreadPrimitive.Root>
  )
}

function ConnectionAlert() {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => subscribeLangGraphError(setMessage), [])

  if (!message) return null
  return (
    <ErrorPrimitive.Root className="mx-auto mb-1 w-[calc(100%-24px)] max-w-[820px] rounded-xl border border-destructive/25 bg-destructive/5 px-3.5 py-2.5 text-sm text-destructive">
      {message}
    </ErrorPrimitive.Root>
  )
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="group mx-auto mb-6 flex max-w-[820px] flex-col items-end">
      <div className="max-w-[70%] rounded-[18px] rounded-br-md bg-accent px-4 py-2.5 text-sm leading-6 text-foreground">
        <MessagePrimitive.Parts components={{ Text: PlainText }} />
      </div>
      <div className="mt-1.5 flex items-center gap-2 px-1 text-[10px] text-muted-foreground">
        <MessageTime />
      </div>
    </MessagePrimitive.Root>
  )
}

function AssistantMessage() {
  const messageId = useAuiState((state) => state.message.id)
  const messageStatus = useAuiState((state) => state.message.status?.type)
  const externalThreadId = useAuiState(
    (state) => state.optional.threadListItem?.externalId,
  )
  const [sourceMap, setSourceMap] = useState<Map<string, ResearchSource>>(() => new Map())
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [activeSourceId, setActiveSourceId] = useState<string>()
  const sources = useMemo(() => [...sourceMap.values()], [sourceMap])

  const registerSource = useCallback((source: ResearchSource) => {
    setSourceMap((current) => {
      const existing = current.get(source.id)
      if (existing && JSON.stringify(existing) === JSON.stringify(source)) return current
      const next = new Map(current)
      next.set(source.id, source)
      return next
    })
  }, [])

  const openSources = useCallback((sourceId?: string) => {
    setActiveSourceId(sourceId)
    setDrawerOpen(true)
  }, [])

  useEffect(() => {
    if (messageStatus !== 'complete' || !externalThreadId) return
    let cancelled = false
    void loadResearchSources(externalThreadId, messageId).then((loaded) => {
      if (cancelled || loaded.length === 0) return
      setSourceMap((current) => {
        const next = new Map(current)
        for (const source of loaded) next.set(source.id, source)
        return next
      })
    })
    return () => {
      cancelled = true
    }
  }, [externalThreadId, messageId, messageStatus])

  return (
    <MessagePrimitive.Root className="group mx-auto mb-8 flex max-w-[820px] gap-3 text-sm leading-7">
      <div className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
        CC
      </div>
      <div className="min-w-0 flex-1">
        <SourceCollectorContext.Provider value={{ sources, registerSource, openSources }}>
          <MessagePrimitive.Parts
            components={{
              Text: MarkdownText,
              Source: SourcePart,
            }}
          />
        </SourceCollectorContext.Provider>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {sources.length > 0 && (
              <button
                type="button"
                onClick={() => openSources()}
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/25 hover:bg-accent hover:text-primary"
              >
                查看引用来源（{sources.length}）
              </button>
            )}
          </div>
          <ActionBarPrimitive.Root hideWhenRunning autohide="not-last" className="flex items-center gap-0.5 text-muted-foreground">
            <ActionBarPrimitive.Copy className="grid size-7 place-items-center rounded-lg transition-colors hover:bg-muted hover:text-foreground" aria-label="复制回答">
              <Copy className="size-3.5" />
            </ActionBarPrimitive.Copy>
          </ActionBarPrimitive.Root>
        </div>
      </div>
      <SourcesDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        sources={sources}
        activeSourceId={activeSourceId}
      />
    </MessagePrimitive.Root>
  )
}

function MarkdownText() {
  return (
    <MarkdownTextPrimitive className="break-words text-foreground [&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-primary/30 [&_blockquote]:pl-3 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_h1]:mb-3 [&_h1]:mt-5 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-5 [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:mt-4 [&_h3]:font-semibold [&_li]:ml-5 [&_ol]:my-2 [&_ol]:list-decimal [&_p]:mb-3 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:bg-muted [&_pre]:p-3 [&_table]:my-4 [&_table]:w-full [&_table]:overflow-hidden [&_table]:rounded-xl [&_table]:border [&_table]:border-border [&_td]:border-b [&_td]:border-r [&_td]:border-border [&_td]:px-3 [&_td]:py-2 [&_th]:border-b [&_th]:border-r [&_th]:border-border [&_th]:bg-muted/70 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_ul]:my-2 [&_ul]:list-disc" />
  )
}

function PlainText() {
  return <MarkdownTextPrimitive className="[&_p]:m-0" />
}

function MessageTime() {
  const createdAt = useAuiState((state) => state.message.createdAt)
  return (
    <time dateTime={createdAt.toISOString()}>
      {new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }).format(createdAt)}
    </time>
  )
}

interface SourceCollectorValue {
  sources: ResearchSource[]
  registerSource: (source: ResearchSource) => void
  openSources: (sourceId?: string) => void
}

const SourceCollectorContext = createContext<SourceCollectorValue | null>(null)

function SourcePart(part: SourceMessagePartProps) {
  const collector = useContext(SourceCollectorContext)
  const source = useMemo(() => normalizeSource(part), [part])

  useEffect(() => {
    collector?.registerSource(source)
  }, [collector, source])

  const index = Math.max(0, collector?.sources.findIndex((item) => item.id === source.id) ?? 0) + 1
  return (
    <button
      type="button"
      onClick={() => collector?.openSources(source.id)}
      className="mx-0.5 align-super text-[10px] font-semibold text-primary hover:underline"
      aria-label={`查看引用 ${index}：${source.title}`}
    >
      [{index}]
    </button>
  )
}

function normalizeSource(part: SourceMessagePartProps): ResearchSource {
  const metadata = Object.values(part.providerMetadata || {}).find(
    (value) => value && typeof value === 'object',
  ) as Record<string, unknown> | undefined
  const page = metadata?.page ?? metadata?.page_number
  const date = metadata?.date ?? metadata?.published_at
  const summary = metadata?.summary ?? metadata?.snippet ?? metadata?.quote
  return {
    id: part.id,
    title: part.title || ('filename' in part && part.filename) || part.url || '未命名来源',
    ...('url' in part && part.url ? { url: part.url } : {}),
    detail: [page ? `P.${String(page)}` : undefined, date ? String(date) : undefined]
      .filter(Boolean)
      .join(' · '),
    summary: typeof summary === 'string' ? summary : undefined,
  }
}

const suggestions = [
  {
    title: '解读财报',
    description: '快速理解公司财报\n关键指标与变化',
    prompt: '请解读最新财报，概括核心业绩、关键指标变化和主要风险。',
    icon: FileSearch,
  },
  {
    title: '公司对比',
    description: '多维度对比分析\n公司经营情况',
    prompt: '请对比两家公司的盈利能力、成长性、资产质量和估值。',
    icon: Building2,
  },
  {
    title: '行业研究',
    description: '分析行业趋势\n与竞争格局',
    prompt: '请分析目标行业的趋势、竞争格局、核心驱动因素和主要风险。',
    icon: BookOpenText,
  },
  {
    title: '指标分析',
    description: '查询与分析\n关键财务指标',
    prompt: '请分析关键财务指标的历史趋势、同业位置和变化原因。',
    icon: Sparkles,
  },
] as const

interface RawLangGraphMessage {
  id?: string
  type?: string
  additional_kwargs?: {
    research_result?: unknown
  }
}

async function loadResearchSources(threadId: string, messageId: string) {
  try {
    const state = await langGraphClient.threads.getState<{
      messages: RawLangGraphMessage[]
    }>(threadId)
    const messages = state.values?.messages || []
    const rawMessage =
      messages.find((message) => message.id === messageId) ||
      [...messages]
        .reverse()
        .find((message) => message.additional_kwargs?.research_result)
    return sourcesFromResearchResult(
      rawMessage?.additional_kwargs?.research_result,
      messageId,
    )
  } catch {
    // Message rendering must remain usable when source hydration fails.
    return []
  }
}

function sourcesFromResearchResult(value: unknown, messageId: string): ResearchSource[] {
  if (!isRecord(value) || !Array.isArray(value.previews)) return []
  const sources: ResearchSource[] = []
  for (const rawPreview of value.previews) {
    if (!isRecord(rawPreview)) continue
    const docId = typeof rawPreview.doc_id === 'string' ? rawPreview.doc_id : ''
    const hits = Array.isArray(rawPreview.hits) ? rawPreview.hits : []
    const metrics = Array.isArray(rawPreview.metrics) ? rawPreview.metrics : []
    const graphPaths = Array.isArray(rawPreview.graph_paths) ? rawPreview.graph_paths : []
    const synthesis = isRecord(rawPreview.synthesis) ? rawPreview.synthesis : undefined
    const citations = Array.isArray(synthesis?.citations) ? synthesis.citations : []

    for (const rawCitation of citations) {
      if (!isRecord(rawCitation) || typeof rawCitation.evidence_id !== 'string') continue
      const evidenceId = rawCitation.evidence_id
      const index = Number(evidenceId.slice(1)) - 1
      const claim = typeof rawCitation.claim === 'string' ? rawCitation.claim : undefined
      const source = sourceForEvidence({
        evidenceId,
        index,
        docId,
        hit: hits[index],
        metric: metrics[index],
        graphPath: graphPaths[index],
        claim,
        messageId,
      })
      if (source) sources.push(source)
    }
  }
  return sources
}

function sourceForEvidence({
  evidenceId,
  index,
  docId,
  hit,
  metric,
  graphPath,
  claim,
  messageId,
}: {
  evidenceId: string
  index: number
  docId: string
  hit: unknown
  metric: unknown
  graphPath: unknown
  claim?: string
  messageId: string
}): ResearchSource | undefined {
  if (index < 0) return undefined
  const kind = evidenceId.charAt(0)
  const base = { id: `${messageId}-${docId}-${evidenceId}` }

  if (kind === 'V' && isRecord(hit)) {
    const metadata = isRecord(hit.metadata) ? hit.metadata : {}
    const page = metadata.page_start ?? metadata.page ?? (
      isRecord(metadata.retrieval) ? metadata.retrieval.page : undefined
    )
    return {
      ...base,
      title: stringValue(metadata.source_section) || stringValue(metadata.section_title) || documentLabel(docId),
      detail: page === undefined ? undefined : `P.${String(page)}`,
      summary: claim || stringValue(hit.content),
    }
  }

  if (kind === 'S' && isRecord(metric)) {
    const pageRange = Array.isArray(metric.page_range) ? metric.page_range : []
    return {
      ...base,
      title: stringValue(metric.source_table_title) || stringValue(metric.source_section) || stringValue(metric.metric_key) || documentLabel(docId),
      detail: pageRange.length > 0 ? `P.${pageRange.join('–')}` : undefined,
      summary: claim,
    }
  }

  if (kind === 'G' && isRecord(graphPath)) {
    return {
      ...base,
      title: '知识图谱证据',
      summary: claim || stringValue(graphPath.summary),
    }
  }
  return undefined
}

function documentLabel(docId: string) {
  return docId ? `文档 ${docId.slice(0, 12)}` : '研究资料'
}

function stringValue(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
