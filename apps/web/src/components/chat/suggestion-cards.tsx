"use client";

import { BarChart3, Code2, Lightbulb, PenLine, Search, Sparkles } from "lucide-react";

const SUGGESTIONS = [
  {
    label: "Analyze Data",
    icon: BarChart3,
    prompt: "Analyze my sales data and tell me what stands out.",
  },
  { label: "Research", icon: Search, prompt: "Research this topic and summarize the key points." },
  { label: "Write", icon: PenLine, prompt: "Help me write a first draft of..." },
  { label: "Code", icon: Code2, prompt: "Help me build an application that..." },
  { label: "Brainstorm", icon: Lightbulb, prompt: "Brainstorm ideas for..." },
  { label: "Summarize", icon: Sparkles, prompt: "Summarize this for me: " },
];

export function SuggestionCards({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {SUGGESTIONS.map((s) => (
        <button
          key={s.label}
          type="button"
          onClick={() => onSelect(s.prompt)}
          className="flex flex-col items-start gap-2 rounded-xl border border-border bg-card px-3.5 py-3 text-left transition-colors hover:border-primary/40 hover:bg-accent"
        >
          <s.icon className="size-4 text-primary" />
          <span className="text-sm font-medium">{s.label}</span>
        </button>
      ))}
    </div>
  );
}
