import * as Dialog from '@radix-ui/react-dialog'
import { ExternalLink, FileText, X } from 'lucide-react'
import { useEffect } from 'react'

export interface ResearchSource {
  id: string
  title: string
  url?: string
  detail?: string
  summary?: string
}

export function SourcesDrawer({
  open,
  onOpenChange,
  sources,
  activeSourceId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  sources: ResearchSource[]
  activeSourceId?: string
}) {
  useEffect(() => {
    if (!open || !activeSourceId) return
    requestAnimationFrame(() => {
      document.getElementById(`source-${activeSourceId}`)?.scrollIntoView({
        block: 'center',
        behavior: 'smooth',
      })
    })
  }, [activeSourceId, open])

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/10 backdrop-blur-[1px]" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(380px,calc(100vw-24px))] flex-col border-l border-border bg-card shadow-xl outline-none transition-transform duration-200 ease-out data-[state=closed]:translate-x-full data-[state=open]:translate-x-0">
          <div className="flex h-16 items-center justify-between border-b border-border px-5">
            <Dialog.Title className="text-base font-semibold">引用来源（{sources.length}）</Dialog.Title>
            <Dialog.Close className="grid size-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" aria-label="关闭引用来源">
              <X className="size-4" />
            </Dialog.Close>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
            {sources.map((source, index) => (
              <article
                key={source.id}
                id={`source-${source.id}`}
                className={`mb-2.5 flex gap-3 rounded-xl border p-3.5 transition-colors ${
                  source.id === activeSourceId
                    ? 'border-primary/30 bg-accent/70'
                    : 'border-border bg-card hover:bg-muted/40'
                }`}
              >
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start gap-2">
                    <FileText className="mt-0.5 size-4 shrink-0 text-primary/70" />
                    <h3 className="min-w-0 flex-1 text-sm font-medium leading-5">{source.title}</h3>
                    {source.url && (
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-muted-foreground transition-colors hover:text-primary"
                        aria-label={`打开原文：${source.title}`}
                      >
                        <ExternalLink className="size-3.5" />
                      </a>
                    )}
                  </div>
                  {source.detail && (
                    <p className="mt-1.5 text-[11px] text-muted-foreground">{source.detail}</p>
                  )}
                  {source.summary && (
                    <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{source.summary}</p>
                  )}
                </div>
              </article>
            ))}
            {sources.length === 0 && (
              <p className="py-12 text-center text-sm text-muted-foreground">当前回答没有可用的引用来源</p>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
