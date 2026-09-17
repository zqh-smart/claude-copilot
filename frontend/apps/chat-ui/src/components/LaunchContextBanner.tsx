import { readLaunchContext, summarizeLaunchContext } from '@/lib/launch-context'
import type { AgentLaunchContext } from '@claude-copilot/contracts'

export function useLaunchContext(search: string): AgentLaunchContext | undefined {
  return readLaunchContext(search)
}

export function LaunchContextBanner({ context }: { context: AgentLaunchContext | undefined }) {
  if (!context) return null
  return (
    <div className="border-b border-border bg-muted/40 px-6 py-2 text-xs text-muted-foreground">
      已从工作台衔接 · {summarizeLaunchContext(context)}
      {context.prompt && (
        <span className="ml-2 rounded bg-background px-2 py-0.5 font-mono text-[11px]">
          预填问题：{context.prompt}
        </span>
      )}
    </div>
  )
}
