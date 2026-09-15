import type { AgentLaunchContext } from '@claude-copilot/contracts'

/**
 * Build the hand-off URL without coupling the workbench to LangGraph SDK types.
 * Resource identifiers are temporary URL fields until the backend issues opaque
 * chat-context IDs; callers must not place document contents or secrets here.
 */
export function buildAgentChatUrl(baseUrl: string, context?: AgentLaunchContext): string {
  const url = new URL(baseUrl, window.location.origin)

  if (context) {
    url.searchParams.set('cc_source', context.source)
    url.searchParams.set('cc_resource', context.resourceId)
    if (context.prompt) url.searchParams.set('cc_prompt', context.prompt)
  }

  return url.toString()
}
