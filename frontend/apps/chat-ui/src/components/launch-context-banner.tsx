"use client";

import type {
  AgentLaunchContext,
  AgentLaunchSource,
} from "@claude-copilot/contracts";
import { useSearchParams } from "next/navigation";

const sourceLabels: Record<AgentLaunchSource, string> = {
  knowledge: "知识库",
  metrics: "指标中心",
  reports: "报告中心",
  research: "研究工作台",
};

function isLaunchSource(value: string | null): value is AgentLaunchSource {
  return value != null && value in sourceLabels;
}

export function LaunchContextBanner() {
  const params = useSearchParams();
  const source = params.get("cc_source");
  const resourceId = params.get("cc_resource");

  if (!isLaunchSource(source) || !resourceId) return null;

  const context: AgentLaunchContext = {
    source,
    resourceId,
    prompt: params.get("cc_prompt") || undefined,
  };

  return (
    <aside className="fixed left-1/2 top-3 z-50 max-w-[min(90vw,48rem)] -translate-x-1/2 rounded-lg border bg-background/95 px-4 py-2 text-sm shadow-sm backdrop-blur">
      <span className="font-medium">来自{sourceLabels[context.source]}</span>
      <span className="mx-2 text-muted-foreground">·</span>
      <code className="break-all text-xs">{context.resourceId}</code>
      {context.prompt ? (
        <span className="ml-2 text-muted-foreground">{context.prompt}</span>
      ) : null}
    </aside>
  );
}
