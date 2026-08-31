"use client";

import { BarChart3, Code2, Lightbulb, PenLine, Search, Sparkles } from "lucide-react";
import Link from "next/link";

const SUGGESTIONS = [
  {
    label: "Analyze Data",
    icon: BarChart3,
    prompt: "Analyze my sales data and tell me what stands out.",
  },
  { label: "Research", icon: Search, prompt: "Research this topic and summarize the key points." },
  { label: "Write", icon: PenLine, prompt: "Help me write a first draft of..." },
  // Unlike the others, "Code" doesn't prefill a chat prompt — plain Chat has no file/command
  // access at all (see docs/architecture/coding-agent.md), so it goes straight to the Code
  // workspace page instead, where a goal actually gets to read/write files and run commands.
  { label: "Code", icon: Code2, href: "/code" },
  { label: "Brainstorm", icon: Lightbulb, prompt: "Brainstorm ideas for..." },
  { label: "Summarize", icon: Sparkles, prompt: "Summarize this for me: " },
] as const;

export function SuggestionCards({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {SUGGESTIONS.map((s) =>
        "href" in s ? (
          <Link
            key={s.label}
            href={s.href}
            className="flex flex-col items-start gap-2 rounded-xl border border-border bg-card px-3.5 py-3 text-left transition-colors hover:border-primary/40 hover:bg-accent"
          >
            <s.icon className="size-4 text-primary" />
            <span className="text-sm font-medium">{s.label}</span>
          </Link>
        ) : (
          <button
            key={s.label}
            type="button"
            onClick={() => onSelect(s.prompt)}
            className="flex flex-col items-start gap-2 rounded-xl border border-border bg-card px-3.5 py-3 text-left transition-colors hover:border-primary/40 hover:bg-accent"
          >
            <s.icon className="size-4 text-primary" />
            <span className="text-sm font-medium">{s.label}</span>
          </button>
        ),
      )}
    </div>
  );
}
