import {
  AttachmentPrimitive,
  ComposerPrimitive,
  useAui,
  useAuiState,
} from '@assistant-ui/react'
import type { AgentLaunchContext } from '@claude-copilot/contracts'
import {
  ArrowUp,
  Building2,
  ChevronDown,
  FilePlus2,
  FileText,
  Library,
  Paperclip,
  Plus,
  Square,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { summarizeLaunchContext } from '@/lib/launch-context'
import { buildRunnableConfig } from '@/runtime/config'

type Scope = 'all' | 'current' | 'selected' | 'uploads'
type ResearchMode = 'quick' | 'deep'

export function ResearchComposer({ launchContext }: { launchContext?: AgentLaunchContext }) {
  const aui = useAui()
  const isRunning = useAuiState((state) => state.thread.isRunning)
  const canAddAttachment = useAuiState((state) => Boolean(state.composer.attachmentAccept))
  const [scope, setScope] = useState<Scope>(launchContext?.resourceId ? 'current' : 'all')
  const [mode, setMode] = useState<ResearchMode>('quick')
  const initializedPrompt = useRef<string | undefined>(undefined)

  useEffect(() => {
    if (!launchContext?.prompt || initializedPrompt.current === launchContext.prompt) return
    if (aui.composer.getState().isEmpty) {
      aui.composer.setText(launchContext.prompt)
      initializedPrompt.current = launchContext.prompt
    }
  }, [aui, launchContext?.prompt])

  useEffect(() => {
    const current = aui.composer.getState().runConfig
    // assistant-ui exposes RunConfig as `{ custom }`, while react-langgraph
    // deliberately forwards the complete object as the SDK `config`.
    const currentRunnable = current as typeof current & ReturnType<typeof buildRunnableConfig>
    const documentConfig = buildRunnableConfig({
      doc_id: scope === 'current' ? launchContext?.resourceId : undefined,
    })
    const configurable: Record<string, unknown> = {
      ...currentRunnable.configurable,
      ...documentConfig.configurable,
    }
    if (scope !== 'current') delete configurable.doc_id
    const nextRunConfig = {
      ...currentRunnable,
      ...documentConfig,
      configurable,
      custom: {
        ...current.custom,
        cc_scope: scope,
        cc_research_mode: mode,
        ...(launchContext?.source ? { cc_source: launchContext.source } : {}),
        ...(launchContext?.resourceId ? { cc_resource: launchContext.resourceId } : {}),
      },
    }
    aui.composer.setRunConfig(nextRunConfig)
  }, [aui, launchContext?.resourceId, launchContext?.source, mode, scope])

  return (
    <div className="shrink-0 bg-gradient-to-t from-background via-background to-background/0 px-3 pb-3 pt-2 sm:px-5 sm:pb-4">
      <ComposerPrimitive.Root className="relative mx-auto w-full max-w-[820px] rounded-[20px] border border-input bg-card p-3 shadow-[0_8px_28px_rgba(27,65,50,0.08)] transition-shadow focus-within:border-primary/35 focus-within:shadow-[0_10px_32px_rgba(27,65,50,0.11)]">
        <ComposerPrimitive.Attachments>
          {({ attachment }) => (
            <AttachmentPrimitive.Root className="mb-2 mr-2 inline-flex max-w-[220px] items-center gap-2 rounded-lg bg-muted px-2.5 py-1.5 text-xs">
              <FileText className="size-3.5 shrink-0 text-primary" />
              <span className="truncate"><AttachmentPrimitive.Name /></span>
              <AttachmentPrimitive.Remove className="text-muted-foreground hover:text-destructive" aria-label={`移除 ${attachment.name}`}>
                <X className="size-3.5" />
              </AttachmentPrimitive.Remove>
            </AttachmentPrimitive.Root>
          )}
        </ComposerPrimitive.Attachments>

        <ComposerPrimitive.Input
          rows={2}
          autoFocus
          placeholder="向金融研究 Agent 提问…"
          className="max-h-40 min-h-[58px] w-full resize-none bg-transparent px-1.5 py-1 text-sm leading-6 outline-none placeholder:text-muted-foreground"
        />

        <div className="mt-2 flex min-w-0 items-end justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-1">
            <ComposerAddMenu canAddAttachment={canAddAttachment} />
            <ComposerMenu
              label={scope === 'all' ? '全部知识库' : scope === 'current' ? '当前文档' : scope === 'selected' ? '指定知识库' : '本次上传文件'}
              prefix="资料范围"
            >
              <MenuOption active={scope === 'all'} onClick={() => setScope('all')}>全部知识库</MenuOption>
              <MenuOption active={scope === 'current'} disabled={!launchContext?.resourceId} onClick={() => setScope('current')}>
                当前文档{launchContext?.resourceId ? ` · ${summarizeLaunchContext(launchContext)}` : ''}
              </MenuOption>
              <MenuOption active={scope === 'selected'} onClick={() => setScope('selected')}>指定知识库</MenuOption>
              <MenuOption active={scope === 'uploads'} onClick={() => setScope('uploads')}>本次上传文件</MenuOption>
            </ComposerMenu>
            <ComposerMenu label={mode === 'quick' ? '快速回答' : '深度研究'}>
              <MenuOption active={mode === 'quick'} onClick={() => setMode('quick')}>快速回答</MenuOption>
              <MenuOption active={mode === 'deep'} onClick={() => setMode('deep')}>深度研究</MenuOption>
            </ComposerMenu>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <span className="mr-1 hidden text-[10px] leading-4 text-muted-foreground lg:block">
              Enter 发送<br />Shift + Enter 换行
            </span>
            <ComposerPrimitive.AddAttachment asChild>
              <button
                type="button"
                className="grid size-9 place-items-center rounded-xl text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35"
                aria-label="添加附件"
                title={canAddAttachment ? '添加附件' : '当前 Agent 尚未配置附件适配器'}
              >
                <Paperclip className="size-[17px]" />
              </button>
            </ComposerPrimitive.AddAttachment>
            {isRunning ? (
              <ComposerPrimitive.Cancel asChild>
                <button type="button" className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground transition-colors hover:bg-primary/90" aria-label="停止生成">
                  <Square className="size-3.5 fill-current" />
                </button>
              </ComposerPrimitive.Cancel>
            ) : (
              <ComposerPrimitive.Send asChild>
                <button type="submit" className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-40" aria-label="发送">
                  <ArrowUp className="size-[18px]" />
                </button>
              </ComposerPrimitive.Send>
            )}
          </div>
        </div>
      </ComposerPrimitive.Root>
    </div>
  )
}

function ComposerAddMenu({ canAddAttachment }: { canAddAttachment: boolean }) {
  return (
    <details className="group relative">
      <summary className="grid size-9 cursor-pointer list-none place-items-center rounded-xl bg-accent text-primary transition-colors hover:bg-primary/10">
        <Plus className="size-[18px] transition-transform group-open:rotate-45" />
      </summary>
      <div className="absolute bottom-11 left-0 z-30 w-52 rounded-xl border border-border bg-popover p-1.5 shadow-lg">
        <ComposerPrimitive.AddAttachment asChild>
          <button
            type="button"
            disabled={!canAddAttachment}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
          >
            <FilePlus2 className="size-4 text-muted-foreground" />
            上传文件
          </button>
        </ComposerPrimitive.AddAttachment>
        <MenuButton icon={Library} label="选择知识库资料" />
        <MenuButton icon={FileText} label="选择已有报告" />
        <MenuButton icon={Building2} label="选择公司 / 标的" />
      </div>
    </details>
  )
}

function ComposerMenu({
  prefix,
  label,
  children,
}: {
  prefix?: string
  label: string
  children: ReactNode
}) {
  return (
    <details className="group relative">
      <summary className="flex h-9 cursor-pointer list-none items-center gap-1.5 rounded-xl px-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
        {prefix && <span className="hidden sm:inline">{prefix}：</span>}
        <span>{label}</span>
        <ChevronDown className="size-3 transition-transform group-open:rotate-180" />
      </summary>
      <div className="absolute bottom-11 left-0 z-30 min-w-44 rounded-xl border border-border bg-popover p-1.5 shadow-lg">
        {children}
      </div>
    </details>
  )
}

function MenuOption({
  active,
  disabled,
  onClick,
  children,
}: {
  active?: boolean
  disabled?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex w-full items-center rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40 ${
        active ? 'bg-accent font-medium text-primary' : ''
      }`}
    >
      {children}
    </button>
  )
}

function MenuButton({ icon: Icon, label }: { icon: typeof Library; label: string }) {
  return (
    <button
      type="button"
      disabled
      title="等待对应资料选择器接入"
      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm opacity-45"
    >
      <Icon className="size-4 text-muted-foreground" />
      {label}
    </button>
  )
}
