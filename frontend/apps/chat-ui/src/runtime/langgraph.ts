/**
 * assistant-ui runtime glue for the LangGraph `agent` graph.
 *
 * Architecture (frozen at P0 acceptance):
 *
 *   assistant-ui  ←  @assistant-ui/react-langgraph  ←  @langchain/langgraph-sdk  ←  LangGraph `:2025`
 *
 * This module deliberately does NOT translate stream events, write its own
 * SSE parser, or fork the protocol. Two seams live here:
 *
 *   1. The LangGraph SDK `Client` — created once, shared by both the
 *      `RemoteThreadListAdapter` and the `useLangGraphRuntime` `load`
 *      callback.
 *   2. The `RemoteThreadListAdapter` — owns thread metadata
 *      (list / initialize / fetch / rename / archive / delete /
 *      generateTitle) by proxying to `client.threads.*`.
 *
 * Everything else is the official runtime's job:
 *   - streaming: `unstable_createLangGraphStream({ client, assistantId })`
 *   - thread persistence: `runtime.load(externalId)` ← `client.threads.getState`
 *   - cancellation: `unstable_allowCancellation: true` (the stream helper
 *     defaults `onDisconnect` to `"cancel"`, so Stop aborts server-side too)
 *   - interrupt handling: provided by the runtime when `load` returns them
 *
 * See https://www.assistant-ui.com/docs/runtimes/langgraph/quickstart and
 * https://www.assistant-ui.com/docs/runtimes/concepts/threads for the
 * contract this module implements.
 */
import type { ThreadMessage } from '@assistant-ui/react'
import type { RemoteThreadListAdapter } from '@assistant-ui/react'
import {
  unstable_createLangGraphStream,
} from '@assistant-ui/react-langgraph'
import { Client } from '@langchain/langgraph-sdk'
import { createAssistantStream } from 'assistant-stream'

import { LANGGRAPH_API_URL, LANGGRAPH_ASSISTANT_ID, langGraphHeaders } from './config'
import {
  clearLangGraphError,
  describeLangGraphFailure,
  notifyLangGraphFailure,
  withTimeout,
} from './connection'

/**
 * Shared LangGraph SDK client. Module-scoped so the SDK can pool connections.
 * The browser hits the LangGraph dev server directly (`:2025`) during
 * development. Production must terminate this at a BFF that injects the
 * LangSmith API key — see apps/chat-ui/RUNTIME.md.
 */
export const langGraphClient = new Client({
  apiUrl: LANGGRAPH_API_URL,
  defaultHeaders: langGraphHeaders(),
})

/**
 * LangGraph has no first-class "archived" concept, so archive state is carried
 * in thread metadata and filtered out of `list()`.
 */
const ARCHIVED_KEY = 'archived'

/**
 * Surface LangGraph threads in the assistant-ui thread list.
 *
 * Contract notes:
 *   - `remoteId === externalId` — assistant-ui stores the same id that
 *     LangGraph uses, so `load(externalId)` and the runtime's stream hooks
 *     line up without a translation table.
 *   - `initialize()` is the seam the runtime uses when the user clicks "新对话".
 *     `create` on `useLangGraphRuntime` is intentionally omitted; the
 *     thread list adapter owns thread creation when it is provided.
 *     (https://www.assistant-ui.com/docs/runtimes/langgraph/threads)
 *   - `nextCursor` is omitted: LangGraph returns the newest page only.
 */
export const langGraphThreadListAdapter: RemoteThreadListAdapter = {
  async list() {
    const records = await langGraphClient.threads.search({
      limit: 50,
      sortBy: 'updated_at',
      sortOrder: 'desc',
    })

    return {
      threads: records
        .filter((thread) => thread.metadata?.[ARCHIVED_KEY] !== true)
        .map((thread) => ({
          status: 'regular',
          remoteId: thread.thread_id,
          externalId: thread.thread_id,
          title: titleOf(thread.metadata),
        })),
    }
  },

  async initialize(_threadId) {
    // LangGraph owns thread id generation; the assistant-ui local id is
    // transient and never surfaced (see `onThreadIdChange` in @/App).
    try {
      const created = await langGraphClient.threads.create({
        metadata: { assistant_id: LANGGRAPH_ASSISTANT_ID },
      })
      clearLangGraphError()
      return { remoteId: created.thread_id, externalId: created.thread_id }
    } catch (reason) {
      throw new Error(describeLangGraphFailure(reason))
    }
  },

  async fetch(threadId) {
    const thread = await langGraphClient.threads.get(threadId)
    return {
      status: thread.metadata?.[ARCHIVED_KEY] === true ? 'archived' : 'regular',
      remoteId: thread.thread_id,
      externalId: thread.thread_id,
      title: titleOf(thread.metadata),
    }
  },

  async rename(remoteId, newTitle) {
    await langGraphClient.threads.update(remoteId, {
      metadata: { title: newTitle },
    })
  },

  async archive(remoteId) {
    await langGraphClient.threads.update(remoteId, {
      metadata: { [ARCHIVED_KEY]: true },
    })
  },

  async unarchive(remoteId) {
    await langGraphClient.threads.update(remoteId, {
      metadata: { [ARCHIVED_KEY]: false },
    })
  },

  async delete(remoteId) {
    await langGraphClient.threads.delete(remoteId)
  },

  /**
   * The adapter contract requires the generated title to be persisted before
   * the returned stream completes, so we await the metadata write and only
   * then replay the title as a single text chunk.
   */
  async generateTitle(remoteId, messages) {
    const candidate = titleFromMessages(messages)
    await langGraphClient.threads.update(remoteId, {
      metadata: { title: candidate },
    })
    return createAssistantStream((controller) => {
      controller.appendText(candidate)
    })
  },
}

function titleFromMessages(messages: readonly ThreadMessage[]): string {
  const lastUser = [...messages].reverse().find((message) => message.role === 'user')
  if (!lastUser || lastUser.role !== 'user') return '新对话'

  const text = lastUser.content
    .map((part) => (part.type === 'text' ? part.text : ''))
    .join('')
    .trim()

  const firstLine = text.split('\n')[0]?.trim() ?? ''
  return firstLine.slice(0, 32) || '新对话'
}

function titleOf(metadata: Record<string, unknown> | null | undefined): string {
  const title = metadata?.title
  if (typeof title === 'string' && title.length > 0) return title

  const docId = metadata?.doc_id
  if (typeof docId === 'string' && docId.length > 0) {
    return `研究 · ${docId.slice(0, 8)}…`
  }

  return '未命名会话'
}

/**
 * Official stream helper plus a timeout around `initialize()`.
 *
 * Cold-start `:2025` outages fail inside `threadListAdapter.initialize`
 * (`POST /threads`). The runtime can swallow that rejection before the run
 * queue settles, leaving `isRunning` stuck. Bounding `initialize()` here
 * makes the stream promise reject, which is the supported seam — still no
 * custom SSE parser.
 */
export const createChatLangGraphStream = () => {
  const stream = unstable_createLangGraphStream({
    client: langGraphClient,
    assistantId: LANGGRAPH_ASSISTANT_ID,
  })

  return async (messages, config) => {
    clearLangGraphError()
    try {
      return await stream(messages, {
        ...config,
        initialize: () => withTimeout(config.initialize()),
      })
    } catch (reason) {
      notifyLangGraphFailure(reason)
      throw reason
    }
  }
}
