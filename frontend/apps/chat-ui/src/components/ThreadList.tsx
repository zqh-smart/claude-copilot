import { ThreadListItemPrimitive, ThreadListPrimitive } from '@assistant-ui/react'
import { MessageSquare, Plus, Trash2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

/**
 * Thread list rail.
 *
 * Backed entirely by `ThreadListPrimitive` / `ThreadListItemPrimitive`; the
 * data comes from `langGraphThreadListAdapter` (see `@/runtime/langgraph`),
 * which owns list / initialize / rename / archive / delete against
 * `client.threads.*`. This component only owns markup.
 */
export function ThreadList() {
  return (
    <ThreadListPrimitive.Root className="flex w-72 shrink-0 flex-col border-r border-border bg-muted/30">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-muted-foreground">Agent Chat</p>
          <p className="text-sm font-semibold">Claude Copilot</p>
        </div>
        <ThreadListPrimitive.New asChild>
          <Button variant="outline" size="sm">
            <Plus className="size-4" /> 新对话
          </Button>
        </ThreadListPrimitive.New>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3">
        <ThreadListPrimitive.Items components={{ ThreadListItem }} />
      </nav>

      <div className="border-t border-border px-4 py-3 text-[11px] text-muted-foreground">
        后端 LangGraph · graph <code>agent</code>
      </div>
    </ThreadListPrimitive.Root>
  )
}

function ThreadListItem() {
  return (
    <ThreadListItemPrimitive.Root
      className={cn(
        'group mb-1 flex items-center justify-between gap-2 rounded-md px-2 py-2 text-sm',
        'hover:bg-accent data-[active]:bg-accent data-[active]:text-accent-foreground',
      )}
    >
      <ThreadListItemPrimitive.Trigger className="flex flex-1 items-center gap-2 overflow-hidden text-left">
        <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
        <ThreadListItemPrimitive.Title fallback="未命名会话" />
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Delete
        aria-label="删除会话"
        className="opacity-0 transition-opacity group-hover:opacity-100"
      >
        <Trash2 className="size-4 text-muted-foreground hover:text-destructive" />
      </ThreadListItemPrimitive.Delete>
    </ThreadListItemPrimitive.Root>
  )
}
