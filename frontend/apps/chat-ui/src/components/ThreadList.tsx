import * as Dialog from '@radix-ui/react-dialog'
import { useAui, useAuiState } from '@assistant-ui/react'
import { Check, MessageSquare, Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import { useMemo, useState } from 'react'

/**
 * History drawer backed by assistant-ui's existing thread-list runtime.
 *
 * Search/grouping are presentation state only. Switching, creating, renaming
 * and deleting always call the runtime owned by `langGraphThreadListAdapter`.
 */
export function ThreadList({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const aui = useAui()
  const threadList = useAuiState((state) => state.threads)
  const [query, setQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draftTitle, setDraftTitle] = useState('')

  const groups = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    const items = threadList.threadItems
      .filter((item) => item.id !== threadList.newThreadId)
      .filter((item) =>
        normalizedQuery
          ? (item.title || '未命名会话').toLocaleLowerCase().includes(normalizedQuery)
          : true,
      )
      .sort((a, b) => (b.lastMessageAt?.getTime() || 0) - (a.lastMessageAt?.getTime() || 0))

    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    return [
      { label: '今天', items: items.filter((item) => (item.lastMessageAt?.getTime() || 0) >= today.getTime()) },
      {
        label: '昨天',
        items: items.filter((item) => {
          const time = item.lastMessageAt?.getTime() || 0
          return time >= yesterday.getTime() && time < today.getTime()
        }),
      },
      { label: '更早', items: items.filter((item) => (item.lastMessageAt?.getTime() || 0) < yesterday.getTime()) },
    ].filter((group) => group.items.length > 0)
  }, [query, threadList])

  const switchThread = async (id: string) => {
    await aui.threads.switchToThread(id)
    onOpenChange(false)
  }

  const createThread = async () => {
    await aui.threads.switchToNewThread()
    onOpenChange(false)
  }

  const saveTitle = async (id: string) => {
    const title = draftTitle.trim()
    if (title) await aui.threads.item({ id }).rename(title)
    setEditingId(null)
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/10 backdrop-blur-[1px] data-[state=closed]:animate-out data-[state=open]:animate-in" />
        <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-[min(312px,calc(100vw-24px))] flex-col border-r border-border bg-card shadow-xl outline-none transition-transform duration-200 ease-out data-[state=closed]:-translate-x-full data-[state=open]:translate-x-0">
          <div className="flex h-16 items-center justify-between px-5">
            <Dialog.Title className="text-base font-semibold">历史会话</Dialog.Title>
            <Dialog.Close className="grid size-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" aria-label="关闭历史会话">
              <X className="size-4" />
            </Dialog.Close>
          </div>

          <div className="px-4 pb-3">
            <label className="flex h-10 items-center gap-2 rounded-xl border border-border bg-background px-3 text-muted-foreground focus-within:border-primary/35">
              <Search className="size-4 shrink-0" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索对话…"
                className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
              />
            </label>
          </div>

          <div className="px-4 pb-2">
            <button
              type="button"
              onClick={() => void createThread()}
              className="flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-primary/20 bg-primary/5 text-sm font-medium text-primary transition-colors hover:bg-primary/10"
            >
              <Plus className="size-4" />
              新建对话
            </button>
          </div>

          <nav className="min-h-0 flex-1 overflow-y-auto px-3 pb-5">
            {threadList.isLoading && (
              <p className="px-2 py-8 text-center text-xs text-muted-foreground">正在加载会话…</p>
            )}
            {!threadList.isLoading && groups.length === 0 && (
              <p className="px-2 py-8 text-center text-xs text-muted-foreground">
                {query ? '没有匹配的对话' : '暂无历史会话'}
              </p>
            )}
            {groups.map((group) => (
              <section key={group.label} className="mt-4">
                <h3 className="mb-1.5 px-2 text-[11px] font-medium text-muted-foreground">{group.label}</h3>
                <div className="space-y-1">
                  {group.items.map((item) => {
                    const active = item.id === threadList.mainThreadId
                    const title = item.title || '未命名会话'
                    return (
                      <div
                        key={item.id}
                        className={`group flex min-h-11 items-center gap-2 rounded-xl px-2.5 transition-colors ${
                          active ? 'bg-accent text-accent-foreground' : 'hover:bg-muted/70'
                        }`}
                      >
                        <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                        {editingId === item.id ? (
                          <>
                            <input
                              autoFocus
                              value={draftTitle}
                              onChange={(event) => setDraftTitle(event.target.value)}
                              onKeyDown={(event) => {
                                if (event.key === 'Enter') void saveTitle(item.id)
                                if (event.key === 'Escape') setEditingId(null)
                              }}
                              className="min-w-0 flex-1 rounded border border-primary/30 bg-card px-1.5 py-1 text-sm outline-none"
                            />
                            <button type="button" onClick={() => void saveTitle(item.id)} aria-label="保存名称">
                              <Check className="size-3.5 text-primary" />
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => void switchThread(item.id)}
                              className="min-w-0 flex-1 py-2 text-left"
                            >
                              <span className="block truncate text-sm">{title}</span>
                              <span className="mt-0.5 block text-[10px] text-muted-foreground">
                                {formatThreadTime(item.lastMessageAt)}
                              </span>
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingId(item.id)
                                setDraftTitle(title)
                              }}
                              className="hidden text-muted-foreground hover:text-foreground group-hover:block"
                              aria-label="重命名会话"
                            >
                              <Pencil className="size-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => void aui.threads.item({ id: item.id }).delete()}
                              className="hidden text-muted-foreground hover:text-destructive group-hover:block"
                              aria-label="删除会话"
                            >
                              <Trash2 className="size-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    )
                  })}
                </div>
              </section>
            ))}
          </nav>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function formatThreadTime(date?: Date) {
  if (!date) return ''
  const today = new Date()
  if (date.toDateString() === today.toDateString()) {
    return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
  }
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(date)
}
