"use client";

import { Copy, RotateCcw, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CitationList } from "@/components/chat/citation-list";
import { MarkdownContent } from "@/components/chat/markdown-content";
import { ToolCallDisplay } from "@/components/chat/tool-call-display";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";

function ActionButton({
  label,
  icon: Icon,
  onClick,
  active,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          aria-label={label}
          className={cn(
            "flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground",
            active && "bg-secondary text-foreground",
          )}
        >
          <Icon className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function AssistantMessage({ message }: { message: ChatMessage }) {
  const [liked, setLiked] = useState<"up" | "down" | null>(null);
  const showEmptyTyping = message.isStreaming && message.content.length === 0;

  async function handleCopy() {
    await navigator.clipboard.writeText(message.content);
    toast.success("Copied to clipboard");
  }

  return (
    <div className="px-4 py-3">
      <div className="mb-1.5 flex items-center gap-2">
        <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Sparkles className="size-3.5" />
        </div>
        <span className="text-sm font-medium">Krixil AI</span>
      </div>

      <div className="pl-8">
        {message.toolCalls?.map((tc) => <ToolCallDisplay key={tc.id} toolCall={tc} />)}

        {showEmptyTyping ? (
          <TypingIndicator />
        ) : (
          <MarkdownContent content={message.content} isStreaming={message.isStreaming} />
        )}

        {message.citations && <CitationList citations={message.citations} />}

        {!message.isStreaming && message.content && (
          <div className="mt-1.5 flex items-center gap-0.5">
            <ActionButton label="Copy" icon={Copy} onClick={handleCopy} />
            <ActionButton
              label="Regenerate"
              icon={RotateCcw}
              onClick={() => toast.info("Regenerate isn't wired up in this phase yet.")}
            />
            <ActionButton
              label="Like"
              icon={ThumbsUp}
              active={liked === "up"}
              onClick={() => setLiked((v) => (v === "up" ? null : "up"))}
            />
            <ActionButton
              label="Dislike"
              icon={ThumbsDown}
              active={liked === "down"}
              onClick={() => setLiked((v) => (v === "down" ? null : "down"))}
            />
          </div>
        )}
      </div>
    </div>
  );
}
