import { useCallback, useMemo, type ReactNode } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { AssistantRuntimeProvider } from '@assistant-ui/react'
import {
  unstable_createLangGraphStream,
  useLangGraphRuntime,
  type LangChainMessage,
  type LangGraphInterruptState,
} from '@assistant-ui/react-langgraph'

import { langGraphClient, langGraphThreadListAdapter } from '@/runtime/langgraph'
import { LANGGRAPH_ASSISTANT_ID } from '@/runtime/config'
import { ChatThread } from '@/routes/ChatThread'
import { ThreadList } from '@/components/ThreadList'
import { LaunchContextBanner, useLaunchContext } from '@/components/LaunchContextBanner'
import { ChatToaster } from '@/components/ui/sonner'

/** URL param holding the active LangGraph thread id. */
const THREAD_PARAM = 'thread'

export default function App() {
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()

  // The `cc_*` handoff params are read on every render and deliberately left
  // in the URL: Acceptance #14 requires the launch context to survive F5 while
  // the prompt is never auto-fired twice (it is displayed, not auto-sent).
  const launchContext = useLaunchContext(location.search)

  // Hard Gate 2 / Acceptance #12: the active thread id lives in the URL so a
  // reload restores history instead of initializing a fresh empty thread.
  const threadId = searchParams.get(THREAD_PARAM) ?? undefined
  const handleThreadIdChange = useCallback(
    (nextThreadId: string | undefined) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (nextThreadId) next.set(THREAD_PARAM, nextThreadId)
          else next.delete(THREAD_PARAM)
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  return (
    <AgentRuntime threadId={threadId} onThreadIdChange={handleThreadIdChange}>
      <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
        <ThreadList />
        <main className="flex flex-1 flex-col overflow-hidden">
          <LaunchContextBanner context={launchContext} />
          <ChatThread />
        </main>
      </div>
      <ChatToaster />
    </AgentRuntime>
  )
}

interface AgentRuntimeProps {
  threadId: string | undefined
  onThreadIdChange: (threadId: string | undefined) => void
  children: ReactNode
}

function AgentRuntime({ threadId, onThreadIdChange, children }: AgentRuntimeProps) {
  // Memoize the client + stream factory so the SDK can reuse its connection
  // pool and the runtime sees a stable reference across renders.
  const client = useMemo(() => langGraphClient, [])
  const stream = useMemo(
    () =>
      unstable_createLangGraphStream({
        client,
        assistantId: LANGGRAPH_ASSISTANT_ID,
      }),
    [client],
  )

  // `load()` is the seam that turns a LangGraph thread id into the messages and
  // interrupts the runtime needs to render history. The thread id is provided
  // by `threadListAdapter.initialize()` / `.fetch()` — that adapter owns thread
  // metadata; this callback owns thread *content*.
  // (https://www.assistant-ui.com/docs/runtimes/langgraph/threads)
  const load = useCallback(async (externalId: string) => {
    const state = await langGraphClient.threads.getState<{
      messages: LangChainMessage[]
    }>(externalId)

    // assistant-ui 0.14 flattened LangGraph's interrupt shape; map explicitly
    // rather than casting so a future SDK field rename fails the typecheck.
    const interrupts: LangGraphInterruptState[] = (state.tasks ?? []).flatMap((task) =>
      task.interrupts.map((interrupt) => ({
        value: interrupt.value,
        resumable: interrupt.resumable,
        when: interrupt.when,
        ns: interrupt.ns,
      })),
    )

    return {
      messages: state.values?.messages ?? [],
      interrupts,
    }
  }, [])

  const runtime = useLangGraphRuntime({
    // Enables the runtime's end-to-end cancellation path: clicking the
    // assistant-ui Stop button propagates through to the LangGraph SDK, whose
    // stream helper defaults `onDisconnect` to "cancel" — gated on
    // Acceptance #15 in apps/chat-ui/RUNTIME.md.
    unstable_allowCancellation: true,

    stream,
    load,

    // The adapter owns the full thread list lifecycle (list / initialize /
    // fetch / rename / archive / delete), so `cloud`, `create` and `delete`
    // are all omitted here.
    unstable_threadListAdapter: langGraphThreadListAdapter,

    // Controlled thread selection: `threadId` in, `onThreadIdChange` out.
    // (@/App keeps both ends in the URL query string.)
    threadId,
    onThreadIdChange,
  })

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
}
