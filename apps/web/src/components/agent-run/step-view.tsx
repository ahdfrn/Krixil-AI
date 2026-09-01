"use client";

import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";

import { MarkdownContent } from "@/components/chat/markdown-content";
import type { AgentStepOut } from "@/lib/api/agents";
import { cn } from "@/lib/utils";

const FILE_TOOLS = new Set(["code.list_files", "host.list_files"]);
const READ_TOOLS = new Set(["code.read_file", "host.read_file"]);
const WRITE_TOOLS = new Set(["code.write_file", "host.write_file"]);
const RUN_TOOLS = new Set(["code.run_command", "host.run_command"]);
const MAX_LISTED_ENTRIES = 20;
// Collapsed by default past this many lines — matches the "expand for the rest" pattern Claude
// Code's own tool-output blocks use, so a full directory tree or file dump doesn't push the run's
// final answer off screen.
const COLLAPSE_LINE_THRESHOLD = 8;

function stringArg(args: unknown, key: string): string | undefined {
  if (typeof args !== "object" || args === null) return undefined;
  const value = (args as Record<string, unknown>)[key];
  return typeof value === "string" ? value : undefined;
}

function summarizeToolCall(toolName: string | null, args: unknown): string {
  const path = stringArg(args, "path");
  const command = stringArg(args, "command");
  const directory = stringArg(args, "directory");

  if (toolName && FILE_TOOLS.has(toolName)) return `List(${path && path !== "." ? path : "."})`;
  if (toolName && READ_TOOLS.has(toolName)) return `Read(${path ?? "?"})`;
  if (toolName && WRITE_TOOLS.has(toolName)) return `Write(${path ?? "?"})`;
  if (toolName && RUN_TOOLS.has(toolName)) {
    return directory && directory !== "." ? `Bash(cd ${directory} && ${command})` : `Bash(${command})`;
  }
  return toolName ?? "Tool call";
}

/** A plain-text, bulleted transcript line — "⏺ Tool(args)" with its result indented underneath
 * behind "⎿" — is literally how Claude Code's own CLI/IDE transcript renders a tool call, no
 * bordered cards, no per-tool icon set, just a bullet and monospace text. This intentionally
 * drops the previous version's boxed/icon-based cards to match that shape exactly rather than
 * approximate it. */
export function StepView({ step }: { step: AgentStepOut }) {
  if (step.type === "tool_call") {
    return (
      <div className="flex items-start gap-2 py-0.5 font-mono text-[13px] leading-relaxed">
        <span className="mt-px shrink-0 text-primary">⏺</span>
        <span className="min-w-0 break-words text-foreground">
          {summarizeToolCall(step.tool_name, step.content.arguments)}
        </span>
      </div>
    );
  }

  if (step.type === "observation") {
    const content = step.content;
    const isPending = content.status === "pending_approval";
    const isError = "error" in content;

    if (isPending) return <ResultLine tone="muted" summary="Paused for approval" />;
    if (isError) {
      return (
        <ResultLine tone="error" summary="Error" defaultOpen>
          <span className="whitespace-pre-wrap break-words">{String(content.error)}</span>
        </ResultLine>
      );
    }

    if (step.tool_name && FILE_TOOLS.has(step.tool_name)) {
      const entries = Array.isArray(content.entries) ? (content.entries as EntrySummary[]) : [];
      return <FileListResult entries={entries} />;
    }
    if (step.tool_name && READ_TOOLS.has(step.tool_name)) {
      const text = typeof content.content === "string" ? content.content : "";
      return <CodeBlockResult content={text} summary={`Read ${countLines(text)} lines`} />;
    }
    if (step.tool_name && WRITE_TOOLS.has(step.tool_name)) {
      return <ResultLine tone="success" summary="Saved" />;
    }
    if (step.tool_name && RUN_TOOLS.has(step.tool_name)) {
      return <CommandResult content={content} />;
    }

    return (
      <ResultLine tone="muted" summary="Result">
        <pre className="overflow-x-auto whitespace-pre-wrap break-words">
          {JSON.stringify(content, null, 2)}
        </pre>
      </ResultLine>
    );
  }

  // final_response — plain flowing prose, no bullet and no bordered card, same as Claude Code's
  // own final answer text (only intermediate tool actions get the "⏺" treatment above).
  return (
    <div className="py-1 text-sm">
      <MarkdownContent content={String(step.content.content ?? "")} />
    </div>
  );
}

/** Ticks once a second while `active`, returning seconds elapsed since `startedAt`. Reading the
 * clock (Date.now()) has to happen inside an effect, not inline during render — calling it there
 * is an impure read that can produce a different result on every render, which is exactly what a
 * ticking display needs, but React's purity rule (rightly) rejects it outside an effect. */
function useElapsedSeconds(startedAt: string, active: boolean): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);

  return Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000));
}

/** The live "still working" line shown while a run's status is "running" — Claude Code's own
 * spinner-with-status-line, right down to the "esc to interrupt" hint next to it. Steps arrive via
 * polling (see lib/api/agents.ts#pollAgentRun), so this is what tells the user more is still
 * coming rather than the transcript having silently stalled. */
export function WorkingIndicator({
  stepCount,
  maxSteps,
  startedAt,
  onStop,
}: {
  stepCount: number;
  maxSteps: number;
  startedAt: string;
  onStop?: () => void;
}) {
  const elapsedSeconds = useElapsedSeconds(startedAt, true);

  return (
    <div className="flex items-center gap-2 py-1 font-mono text-[13px] text-muted-foreground">
      <span className="relative flex size-2.5 shrink-0">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/50" />
        <span className="relative inline-flex size-2.5 rounded-full bg-primary" />
      </span>
      <span>
        Working… ({elapsedSeconds}s · {stepCount}/{maxSteps} steps)
      </span>
      {onStop && (
        <button
          type="button"
          onClick={onStop}
          className="ml-1 rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground hover:border-destructive/50 hover:text-destructive"
        >
          esc to interrupt
        </button>
      )}
    </div>
  );
}

function countLines(text: string): number {
  return text === "" ? 0 : text.split("\n").length;
}

/** The shared "⎿ result" line every observation renders as — plain indented monospace text, no
 * border, no background, no icon set — matching a real terminal's continuation prefix instead of
 * a chat "card". Auto-collapses long content behind a click-to-expand toggle. */
function ResultLine({
  tone,
  summary,
  children,
  defaultOpen = false,
  collapsible = false,
}: {
  tone: "muted" | "success" | "error";
  summary: string;
  children?: React.ReactNode;
  defaultOpen?: boolean;
  collapsible?: boolean;
}) {
  // "open" only governs visibility when there's actually a toggle to collapse behind (collapsible
  // === true) — non-collapsible results have no affordance to reopen them, so they must always
  // render their content regardless of this state.
  const [open, setOpen] = useState(defaultOpen);
  const expanded = !collapsible || open;
  const summaryColor =
    tone === "error" ? "text-destructive" : tone === "success" ? "text-emerald-600 dark:text-emerald-500" : "text-muted-foreground";

  return (
    <div className="pl-1 font-mono text-[13px] leading-relaxed">
      <button
        type="button"
        onClick={() => collapsible && setOpen((v) => !v)}
        className={cn(
          "flex items-start gap-1 text-muted-foreground",
          collapsible && "cursor-pointer hover:text-foreground",
        )}
      >
        <span className="shrink-0">⎿</span>
        {collapsible && (
          <ChevronRight className={cn("mt-1 size-3 shrink-0 transition-transform", expanded && "rotate-90")} />
        )}
        <span className={summaryColor}>{summary}</span>
      </button>
      {expanded && children && (
        <div className="ml-4 border-l border-border/60 pl-2 text-muted-foreground">{children}</div>
      )}
    </div>
  );
}

interface EntrySummary {
  name: string;
  path: string;
  is_dir: boolean;
  size_bytes: number | null;
}

function FileListResult({ entries }: { entries: EntrySummary[] }) {
  if (entries.length === 0) return <ResultLine tone="muted" summary="No files here" />;
  const shown = entries.slice(0, MAX_LISTED_ENTRIES);
  const remaining = entries.length - shown.length;
  return (
    <ResultLine
      tone="muted"
      summary={`Listed ${entries.length} ${entries.length === 1 ? "path" : "paths"}`}
      collapsible={entries.length > COLLAPSE_LINE_THRESHOLD}
    >
      <div className="flex flex-col">
        {shown.map((entry) => (
          <span key={entry.path} className="truncate">
            {entry.is_dir ? `${entry.name}/` : entry.name}
          </span>
        ))}
        {remaining > 0 && <span className="text-muted-foreground/70">…and {remaining} more</span>}
      </div>
    </ResultLine>
  );
}

function CodeBlockResult({ content, summary }: { content: string; summary: string }) {
  return (
    <ResultLine tone="muted" summary={summary} collapsible={countLines(content) > COLLAPSE_LINE_THRESHOLD}>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words">{content}</pre>
    </ResultLine>
  );
}

function CommandResult({ content }: { content: Record<string, unknown> }) {
  const stdout = typeof content.stdout === "string" ? content.stdout : "";
  const stderr = typeof content.stderr === "string" ? content.stderr : "";
  const exitCode = content.exit_code;
  const timedOut = content.timed_out === true;
  const ok = exitCode === 0 && !timedOut;
  const combined = [stdout, stderr].filter(Boolean).join("\n");

  return (
    <ResultLine
      tone={timedOut ? "error" : ok ? "success" : "error"}
      summary={timedOut ? "Timed out" : `Exit ${String(exitCode)}`}
      collapsible={countLines(combined) > COLLAPSE_LINE_THRESHOLD}
      defaultOpen
    >
      {stdout && <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-foreground">{stdout}</pre>}
      {stderr && <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-destructive">{stderr}</pre>}
      {!stdout && !stderr && <span className="text-muted-foreground/70">(no output)</span>}
    </ResultLine>
  );
}
