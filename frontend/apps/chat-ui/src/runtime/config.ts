/**
 * Build-time LangGraph configuration.
 *
 * These values are baked into the client bundle by Vite's `define` plugin. Only
 * public, non-secret configuration is allowed here. Long-lived secrets
 * (LangSmith API keys, server-to-server auth) MUST NOT be exposed via
 * VITE_*-prefixed env vars — see RUNTIME.md for the BFF-only secret path.
 */
import type { Config } from '@langchain/langgraph-sdk'

declare const __LANGGRAPH_API_URL__: string
declare const __LANGGRAPH_ASSISTANT_ID__: string

export const LANGGRAPH_API_URL = __LANGGRAPH_API_URL__
export const LANGGRAPH_ASSISTANT_ID = __LANGGRAPH_ASSISTANT_ID__

export function langGraphHeaders(): Record<string, string> {
  return {
    'X-Chat-Client': 'claude-copilot-chat-ui',
  }
}

/**
 * Runtime config passed to LangGraph runs. The `configurable` payload carries
 * Workbench handoff context (doc id, follow-up prompt, chat memory session) so
 * the backend agent knows what the user was looking at when the chat started.
 *
 * NOTE (P0): nothing calls this yet. In assistant-ui 0.15 the `load()` seam no
 * longer forwards a run config to `threads.getState()`, so the handoff has to
 * travel through the run itself (`thread.append({ runConfig })` /
 * `composer.setRunConfig()` → `createLangGraphStream` → `runs.stream`). Wiring
 * that is P1; see apps/chat-ui/RUNTIME.md "Known gaps".
 */
export interface AgentRuntimeConfig {
  doc_id?: string
  doc_id_b?: string
  chat_memory_session_id?: string
}

export function buildRunnableConfig(context: AgentRuntimeConfig = {}): Config {
  const configurable: Record<string, unknown> = {}
  if (context.doc_id) configurable.doc_id = context.doc_id
  if (context.doc_id_b) configurable.doc_id_b = context.doc_id_b
  if (context.chat_memory_session_id) {
    configurable.chat_memory_session_id = context.chat_memory_session_id
  }
  return {
    configurable,
    recursion_limit: 25,
  }
}
