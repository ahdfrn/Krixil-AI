"use client";

import { FileText } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Citation } from "@/types/chat";

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;

  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border pt-3">
      <span className="text-xs text-muted-foreground">Sources:</span>
      {citations.map((citation, i) => (
        <Tooltip key={citation.id}>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 rounded-full border border-border bg-secondary/50 px-2 py-0.5 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <FileText className="size-3" />
              <span>
                [{i + 1}] {citation.documentName}
                {citation.page ? `, p.${citation.page}` : ""}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent className="max-w-64">{citation.snippet}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}
