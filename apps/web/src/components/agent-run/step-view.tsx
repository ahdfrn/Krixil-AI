"use client";

import { Folder, File as FileIcon, TriangleAlert, Wrench } from "lucide-react";

import { MarkdownContent } from "@/components/chat/markdown-content";
import type { AgentStepOut } from "@/lib/api/agents";

const FILE_TOOLS = new Set(["code.list_files", "host.list_files"]);
const READ_TOOLS = new Set(["code.read_file", "host.read_file"]);
const WRITE_TOOLS = new Set(["code.write_file", "host.write_file"]);
const RUN_TOOLS = new Set(["code.run_command", "host.run_command"]);
const MAX_LISTED_ENTRIES = 20;

function stringArg(args: unknown, key: string): string | undefined {
  if (typeof args !== "object" || args === null) return undefined;
  const value = (args as Record<string, unknown>)[key];
  return typeof value === "string" ? value : undefined;
}

function summarizeToolCall(toolName: string | null, args: unknown): string {
  const path = stringArg(args, "path");
  const command = stringArg(args, "command");
  const directory = stringArg(args, "directory");

  if (toolName && FILE_TOOLS.has(toolName)) return `Listed ${path && path !== "." ? path : "files"}`;
  if (toolName && READ_TOOLS.has(toolName)) return `Read ${path ?? "a file"}`;
  if (toolName && WRITE_TOOLS.has(toolName)) return `Wrote ${path ?? "a file"}`;
  if (toolName && RUN_TOOLS.has(toolName)) {
    return directory && directory !== "." ? `Ran in ${directory}: ${command}` : `Ran: ${command}`;
  }
  return `Called ${toolName}`;
}

/** Tool-call and observation steps render the raw JSON payload by default — fine for a small
 * result (e.g. usage.get_summary), unreadable for a real directory listing or file content
 * (caught live: browsing a real project folder in "This Computer" mode dumped hundreds of file
 * entries as one giant escaped-JSON blob). The code and host tool families get a proper,
 * tool-aware rendering instead; anything else still falls back to the JSON dump. */
export function StepView({ step }: { step: AgentStepOut }) {
  if (step.type === "tool_call") {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-border bg-secondary/30 p-2.5 text-xs">
        <Wrench className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 break-words font-medium">
          {summarizeToolCall(step.tool_name, step.content.arguments)}
        </span>
      </div>
    );
  }

  if (step.type === "observation") {
    const content = step.content;
    const isPending = content.status === "pending_approval";
    const isError = "error" in content;

    if (isPending) {
      return (
        <div className="rounded-lg border border-border bg-secondary/30 p-2.5 text-xs">
          <span className="font-medium">Paused for approval</span>
        </div>
      );
    }
    if (isError) {
      return (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-2.5 text-xs text-destructive">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span className="min-w-0 break-words">{String(content.error)}</span>
        </div>
      );
    }

    if (step.tool_name && FILE_TOOLS.has(step.tool_name)) {
      const entries = Array.isArray(content.entries) ? (content.entries as EntrySummary[]) : [];
      return <FileListResult entries={entries} />;
    }
    if (step.tool_name && READ_TOOLS.has(step.tool_name)) {
      return <CodeResult content={typeof content.content === "string" ? content.content : ""} />;
    }
    if (step.tool_name && WRITE_TOOLS.has(step.tool_name)) {
      return (
        <div className="rounded-lg border border-border bg-secondary/30 p-2.5 text-xs text-muted-foreground">
          Saved.
        </div>
      );
    }
    if (step.tool_name && RUN_TOOLS.has(step.tool_name)) {
      return <CommandResult content={content} />;
    }

    return (
      <div className="rounded-lg border border-border bg-secondary/30 p-2.5 text-xs">
        <span className="font-medium">Result</span>
        <pre className="mt-1 overflow-x-auto text-muted-foreground">
          {JSON.stringify(content, null, 2)}
        </pre>
      </div>
    );
  }

  // final_response
  return (
    <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
      <MarkdownContent content={String(step.content.content ?? "")} />
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
  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-secondary/30 p-2.5 text-xs text-muted-foreground">
        No files here.
      </div>
    );
  }
  const shown = entries.slice(0, MAX_LISTED_ENTRIES);
  const remaining = entries.length - shown.length;
  return (
    <div className="rounded-lg border border-border bg-secondary/30 p-2.5 text-xs">
      <div className="flex flex-col gap-1">
        {shown.map((entry) => (
          <div key={entry.path} className="flex items-center gap-1.5 text-muted-foreground">
            {entry.is_dir ? (
              <Folder className="size-3 shrink-0" />
            ) : (
              <FileIcon className="size-3 shrink-0" />
            )}
            <span className="truncate">{entry.name}</span>
          </div>
        ))}
      </div>
      {remaining > 0 && (
        <p className="mt-1 text-muted-foreground/70">and {remaining} more</p>
      )}
    </div>
  );
}

function CodeResult({ content }: { content: string }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/30 p-2.5 text-xs">
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-muted-foreground">
        {content}
      </pre>
    </div>
  );
}

function CommandResult({ content }: { content: Record<string, unknown> }) {
  const stdout = typeof content.stdout === "string" ? content.stdout : "";
  const stderr = typeof content.stderr === "string" ? content.stderr : "";
  const exitCode = content.exit_code;
  const timedOut = content.timed_out === true;
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-border bg-secondary/30 p-2.5 text-xs">
      <div className="flex items-center gap-2 text-muted-foreground">
        <span>exit code {String(exitCode)}</span>
        {timedOut && <span className="text-destructive">timed out</span>}
      </div>
      {stdout && (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-foreground">{stdout}</pre>
      )}
      {stderr && (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-destructive">{stderr}</pre>
      )}
      {!stdout && !stderr && <p className="text-muted-foreground/70">(no output)</p>}
    </div>
  );
}
