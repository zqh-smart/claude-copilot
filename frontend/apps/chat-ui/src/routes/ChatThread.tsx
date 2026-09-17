import {
  AuiIf,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from '@assistant-ui/react'
import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown'
import { Send, Square } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { subscribeLangGraphError } from '@/runtime/connection'

/**
 * The chat surface.
 *
 * Built from assistant-ui primitives only — this file owns markup and nothing
 * else. Streaming, thread persistence, interrupts and cancellation all live in
 * the runtime wired up in `@/App`. Tool UI / Generative UI / citations will
 * attach here later (via `MessagePrimitive.Parts` `components.tools`) without
 * changing the surrounding layout.
 */
export function ChatThread() {
  return (
    <ThreadPrimitive.Root className="flex flex-1 flex-col overflow-hidden">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-6 py-6">
        <AuiIf condition={(s) => s.thread.isEmpty}>
          <p className="mx-auto mt-24 max-w-xl text-center text-sm text-muted-foreground">
            你好，我是 Claude Copilot 的金融研究 Agent。可以从左侧选择已有对话，或直接向我提问。
          </p>
        </AuiIf>
        <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
      </ThreadPrimitive.Viewport>

      <div className="flex justify-center py-2">
        <ThreadPrimitive.ScrollToBottom asChild>
          <Button variant="outline" size="sm">
            回到底部
          </Button>
        </ThreadPrimitive.ScrollToBottom>
      </div>

      <ConnectionAlert />

      <ComposerPrimitive.Root className="border-t border-border bg-background px-6 py-4">
        <ComposerPrimitive.Input
          rows={1}
          placeholder="向 Claude Copilot 提问…"
          className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
        />
        <div className="mt-3 flex items-center justify-end gap-2">
          <CancelButton />
          <ComposerPrimitive.Send asChild>
            <Button type="submit" size="icon" aria-label="发送">
              <Send className="size-4" />
            </Button>
          </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </ThreadPrimitive.Root>
  )
}

/**
 * Cancellation is only meaningful while a run is in flight. Hiding the button
 * otherwise keeps the composer stable; `ComposerPrimitive.Cancel` itself is
 * disabled when the runtime reports nothing to cancel.
 */
function CancelButton() {
  const isRunning = useAuiState((s) => s.thread.isRunning)
  const [connectionError, setConnectionError] = useState<string | null>(null)

  useEffect(() => subscribeLangGraphError(setConnectionError), [])

  if (!isRunning || connectionError) return null
  return (
    <ComposerPrimitive.Cancel asChild>
      <Button type="button" variant="outline" size="icon" aria-label="停止">
        <Square className="size-4" />
      </Button>
    </ComposerPrimitive.Cancel>
  )
}

function ConnectionAlert() {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => subscribeLangGraphError(setMessage), [])

  if (!message) return null
  return (
    <ErrorPrimitive.Root className="mx-6 mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {message}
    </ErrorPrimitive.Root>
  )
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="mx-auto mb-4 flex max-w-3xl justify-end">
      <div className="max-w-[80%] rounded-2xl bg-primary px-4 py-2 text-sm text-primary-foreground">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  )
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="mx-auto mb-6 max-w-3xl text-sm leading-relaxed">
      <MessagePrimitive.Parts components={{ Text: MarkdownText }} />
    </MessagePrimitive.Root>
  )
}

/**
 * We intentionally keep the official markdown renderer for the first migration
 * round. Tool UI / citations will override `components.tools` in a follow-up
 * without touching the surrounding Thread layout.
 */
function MarkdownText() {
  return <MarkdownTextPrimitive className="[&_a]:underline [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_li]:ml-4 [&_ol]:list-decimal [&_p]:mb-2 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:p-3 [&_ul]:list-disc" />
}
