"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function CopyableCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="group/cmd relative rounded-md border border-border bg-secondary/20 px-3 py-2 font-mono text-xs">
      <pre className="overflow-x-auto whitespace-pre-wrap pr-7">{command}</pre>
      <button
        type="button"
        onClick={() => void handleCopy()}
        aria-label="Copy"
        className="absolute top-1.5 right-1.5 flex size-6 items-center justify-center rounded text-muted-foreground opacity-0 hover:bg-secondary hover:text-foreground group-hover/cmd:opacity-100"
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
    </div>
  );
}
