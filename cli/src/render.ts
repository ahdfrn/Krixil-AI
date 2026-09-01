/**
 * Pure, framework-free step-summarization logic — shared by ui/Transcript.tsx (Ink/JSX, for the
 * interactive REPL) and runOnce.ts (plain console.log, for `kirxil run` and any piped/non-TTY
 * use where an Ink app can't render). One implementation, two renderers, so both stay identical
 * the way apps/web/.../step-view.tsx and cli-python/krixil_cli/render.py already do.
 */

import type { AgentStep } from "./api.js";

const FILE_TOOLS = new Set(["host.list_files"]);
const READ_TOOLS = new Set(["host.read_file"]);
const WRITE_TOOLS = new Set(["host.write_file"]);
const EDIT_TOOLS = new Set(["host.edit_file"]);
const SEARCH_TOOLS = new Set(["host.search_files"]);
const DELETE_TOOLS = new Set(["host.delete_file"]);
const RUN_TOOLS = new Set(["host.run_command"]);
export const MAX_LISTED_ENTRIES = 20;
export const MAX_OUTPUT_LINES = 40;

export type Tone = "success" | "error" | "muted";

export interface ObservationSummary {
  summary: string;
  body: string[];
  tone: Tone;
}

export function summarizeToolCall(toolName: string | null, args: Record<string, unknown>): string {
  const path = typeof args.path === "string" ? args.path : undefined;
  const command = typeof args.command === "string" ? args.command : undefined;
  const directory = typeof args.directory === "string" ? args.directory : undefined;
  const pattern = typeof args.pattern === "string" ? args.pattern : undefined;

  if (toolName && FILE_TOOLS.has(toolName)) return `List(${path && path !== "." ? path : "."})`;
  if (toolName && READ_TOOLS.has(toolName)) return `Read(${path ?? "?"})`;
  if (toolName && WRITE_TOOLS.has(toolName)) return `Write(${path ?? "?"})`;
  if (toolName && EDIT_TOOLS.has(toolName)) return `Edit(${path ?? "?"})`;
  if (toolName && SEARCH_TOOLS.has(toolName)) return `Search(${pattern ?? "?"})`;
  if (toolName && DELETE_TOOLS.has(toolName)) return `Delete(${path ?? "?"})`;
  if (toolName && RUN_TOOLS.has(toolName)) {
    return directory && directory !== "." ? `Bash(cd ${directory} && ${command})` : `Bash(${command})`;
  }
  return toolName ?? "Tool call";
}

export function trimLines(lines: string[]): string[] {
  if (lines.length <= MAX_OUTPUT_LINES) return lines;
  return [...lines.slice(0, MAX_OUTPUT_LINES), `… and ${lines.length - MAX_OUTPUT_LINES} more lines`];
}

export interface ApprovalPrompt {
  title: string;
  detail: string;
}

/**
 * What to show while a run is paused at status "waiting_approval" (app/agents/runner.py) — built
 * from the tool_call step already in hand (its summarizeToolCall rendering) plus the risk level
 * fetched from the execution itself (GET /tools/executions/{id}), same two pieces of information
 * the web app's Agents page shows for the same pause (apps/web/.../agents/page.tsx).
 */
export function describeApprovalPrompt(toolName: string, riskLevel: string, args: Record<string, unknown>): ApprovalPrompt {
  return {
    title: summarizeToolCall(toolName, args),
    detail: `${riskLevel.toUpperCase()} risk — approve to run it for real, or reject to stop this goal.`,
  };
}

export function describeObservation(step: AgentStep): ObservationSummary {
  const content = step.content;
  const toolName = step.tool_name;

  if (content.status === "pending_approval") return { summary: "Paused for approval", body: [], tone: "muted" };
  if ("error" in content) return { summary: "Error", body: [String(content.error)], tone: "error" };

  if (toolName && FILE_TOOLS.has(toolName)) {
    const entries = (Array.isArray(content.entries) ? content.entries : []) as { name: string; is_dir: boolean }[];
    if (entries.length === 0) return { summary: "No files here", body: [], tone: "muted" };
    const shown = entries.slice(0, MAX_LISTED_ENTRIES);
    const body = shown.map((e) => `${e.is_dir ? "/" : ""}${e.name}`);
    if (entries.length > shown.length) body.push(`…and ${entries.length - shown.length} more`);
    return { summary: `Listed ${entries.length} paths`, body, tone: "muted" };
  }

  if (toolName && READ_TOOLS.has(toolName)) {
    const text = typeof content.content === "string" ? content.content : "";
    const body = text.split("\n");
    return { summary: `Read ${body.length} lines`, body, tone: "muted" };
  }

  if (toolName && WRITE_TOOLS.has(toolName)) return { summary: "Saved", body: [], tone: "success" };

  if (toolName && EDIT_TOOLS.has(toolName)) return { summary: "Edited", body: [], tone: "success" };

  if (toolName && DELETE_TOOLS.has(toolName)) return { summary: "Deleted", body: [], tone: "success" };

  if (toolName && SEARCH_TOOLS.has(toolName)) {
    const results = (Array.isArray(content.results) ? content.results : []) as {
      path: string;
      line_number: number;
      line: string;
    }[];
    if (results.length === 0) return { summary: "No matches", body: [], tone: "muted" };
    const shown = results.slice(0, MAX_LISTED_ENTRIES);
    const body = shown.map((r) => `${r.path}:${r.line_number}: ${r.line}`);
    if (results.length > shown.length) body.push(`…and ${results.length - shown.length} more`);
    return { summary: `${results.length} match${results.length === 1 ? "" : "es"}`, body, tone: "muted" };
  }

  if (toolName && RUN_TOOLS.has(toolName)) {
    const exitCode = content.exit_code;
    const timedOut = content.timed_out === true;
    const ok = exitCode === 0 && !timedOut;
    const summary = timedOut ? "Timed out" : `Exit ${String(exitCode)}`;
    const stdout = typeof content.stdout === "string" ? content.stdout : "";
    const stderr = typeof content.stderr === "string" ? content.stderr : "";
    const body = [...stdout.split("\n"), ...stderr.split("\n")].filter((l) => l !== "");
    return { summary, body, tone: timedOut ? "error" : ok ? "success" : "error" };
  }

  return { summary: "Result", body: [JSON.stringify(content)], tone: "muted" };
}
