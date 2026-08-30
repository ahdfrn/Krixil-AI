"use client";

import { ChevronDown, CircleCheck, Loader2 } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { ToolCallSummary } from "@/types/chat";

/**
 * Shows what the AI is doing in plain language — never a raw tool name, endpoint, or payload.
 * Per the master prompt: "Jangan menampilkan technical information yang membingungkan user
 * biasa." Steps are shown as a live checklist while running; once done, it collapses to a single
 * summary line with an optional "View details" expansion.
 */
export function ToolCallDisplay({ toolCall }: { toolCall: ToolCallSummary }) {
  const isRunning = toolCall.steps.some((s) => s.status === "running");

  if (isRunning) {
    return (
      <div className="my-2 flex flex-col gap-1.5 rounded-lg border border-border bg-secondary/30 px-3 py-2.5 text-sm">
        {toolCall.steps.map((step) => (
          <div key={step.id} className="flex items-center gap-2 text-muted-foreground">
            {step.status === "running" ? (
              <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
            ) : (
              <CircleCheck className="size-3.5 shrink-0 text-primary" />
            )}
            <span className={cn(step.status === "done" && "line-through opacity-70")}>
              {step.label}
            </span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <Collapsible className="my-2 rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <CircleCheck className="size-3.5 shrink-0 text-primary" />
        <span>{toolCall.summary}</span>
        {toolCall.details && (
          <CollapsibleTrigger className="group ml-auto flex items-center gap-1 text-xs hover:text-foreground">
            View details
            <ChevronDown className="size-3 transition-transform group-data-[state=open]:rotate-180" />
          </CollapsibleTrigger>
        )}
      </div>
      {toolCall.details && (
        <CollapsibleContent className="mt-2 border-t border-border pt-2 text-xs text-muted-foreground">
          {toolCall.details}
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}
