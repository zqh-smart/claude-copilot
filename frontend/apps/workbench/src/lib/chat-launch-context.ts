import { shallowRef, type ShallowRef } from 'vue'

import type { AgentLaunchContext } from '@claude-copilot/contracts'

/**
 * The Workbench → Agent Chat hand-off context.
 *
 * The top bar owns the "Agent Chat" button, but only the *active view* knows
 * which business resource the user is looking at. Views publish their context
 * here; `AppLayout.openAgentChat()` reads it at click time and turns it into the
 * `cc_*` query params consumed by `apps/chat-ui/src/lib/launch-context.ts`.
 *
 * Deliberately a module-scoped ref rather than a store: the context is
 * view-scoped and must be released when the view unmounts, so it does not
 * belong in a long-lived Pinia store. Views MUST clear it on unmount —
 * otherwise navigating to a view that publishes nothing (e.g. `/upload`) would
 * still hand off the previous view's resource.
 *
 * Never place document contents, secrets or trace ids here: this value travels
 * in the URL. Resource identifiers only.
 */
const current = shallowRef<AgentLaunchContext | undefined>(undefined)

/** Publish (or replace) the active view's hand-off context. */
export function setChatLaunchContext(context: AgentLaunchContext | undefined) {
  current.value = context
}

/** Release the hand-off context. Call from `onUnmounted` in every publisher. */
export function clearChatLaunchContext() {
  current.value = undefined
}

/** Read-only reactive handle used by the top bar. */
export function useChatLaunchContext(): ShallowRef<AgentLaunchContext | undefined> {
  return current
}
