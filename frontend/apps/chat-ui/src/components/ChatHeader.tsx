import { Menu } from 'lucide-react'

export function ChatHeader({ onOpenHistory }: { onOpenHistory: () => void }) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-card/95 px-4 sm:px-5">
      <button
        type="button"
        onClick={onOpenHistory}
        className="flex h-9 items-center gap-2.5 rounded-xl px-2.5 text-sm font-semibold transition-colors hover:bg-muted"
        aria-label="打开历史会话"
      >
        <Menu className="size-[18px] text-muted-foreground" />
        <span>研究对话</span>
      </button>

      <div className="flex h-9 items-center gap-2 px-2 text-xs text-muted-foreground">
        <span className="grid size-7 place-items-center rounded-full bg-accent font-semibold text-primary">
          研
        </span>
        <span className="hidden sm:inline">研究员</span>
      </div>
    </header>
  )
}
