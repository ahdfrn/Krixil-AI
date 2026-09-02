/**
 * Pure, framework-free step-summarization logic — shared by ui/Transcript.tsx (Ink/JSX, for the
 * interactive REPL) and runOnce.ts (plain console.log, for `kirxil run` and any piped/non-TTY
 * use where an Ink app can't render). One implementation, two renderers, so both stay identical
 * the way apps/web/.../step-view.tsx and cli-python/krixil_cli/render.py already do.
 */

import type { AgentStep } from "./api.js";

// Every host.* tool has a code.* twin with identical semantics, scoped to the sandboxed workspace
// instead of the real host filesystem (app/tools/code_tools.py mirrors app/tools/host_tools.py
// name-for-name) — both need to render the same way here, not just the host.* one.
const FILE_TOOLS = new Set(["host.list_files", "code.list_files"]);
const READ_TOOLS = new Set(["host.read_file", "code.read_file"]);
const WRITE_TOOLS = new Set(["host.write_file", "code.write_file"]);
const EDIT_TOOLS = new Set(["host.edit_file", "code.edit_file"]);
const SEARCH_TOOLS = new Set(["host.search_files", "code.search_files"]);
const DELETE_TOOLS = new Set(["host.delete_file", "code.delete_file"]);
const RUN_TOOLS = new Set(["host.run_command", "code.run_command"]);
export const MAX_LISTED_ENTRIES = 20;
export const MAX_OUTPUT_LINES = 40;

/** Matches a command that's actually invoking a test runner — used to derive both the "Running
 * tests…" in-flight label and the real test-attempt count, from the same real transcript data
 * rather than two separately-maintained heuristics. */
const TEST_COMMAND_PATTERN = /\b(pytest|py\.test|npm (?:run )?test|yarn test|pnpm test|vitest|jest|go test|cargo test|mvn test|gradle test)\b/i;

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

/** A short label for the tool call currently in flight (no observation yet) — derived from the
 * real tool name/command, not a fabricated fixed state machine with steps this loop doesn't
 * actually have. Returns null for an unknown/missing tool name so callers can fall back to a
 * generic "Working…". */
export function describeInFlightStep(toolName: string | null, args: Record<string, unknown>): string | null {
  if (!toolName) return null;
  if (RUN_TOOLS.has(toolName)) {
    const command = typeof args.command === "string" ? args.command : "";
    return TEST_COMMAND_PATTERN.test(command) ? "Running tests…" : "Running a command…";
  }
  if (SEARCH_TOOLS.has(toolName)) return "Searching…";
  if (EDIT_TOOLS.has(toolName)) return "Editing…";
  if (WRITE_TOOLS.has(toolName)) return "Writing…";
  if (READ_TOOLS.has(toolName)) return "Reading…";
  if (FILE_TOOLS.has(toolName)) return "Listing files…";
  if (DELETE_TOOLS.has(toolName)) return "Deleting…";
  return "Working…";
}

export type TestOutcome = "passed" | "failed" | "pending";

/** The real pass/fail sequence of every test-runner invocation in this transcript, in order — the
 * self-healing loop's own real retry-and-fix cycle (app/agents/runner.py's MAX_RETRIES), read
 * back from the actual tool_call/observation pairs rather than a fabricated named state machine
 * ("DIAGNOSE"/"FIX" aren't real backend states this loop tags steps with). "pending" is a real
 * attempt that's been started but has no observation yet (still running, or paused on a HIGH-risk
 * approval) — kept in the sequence rather than dropped, so a live count doesn't jump when it
 * resolves. */
export function testAttemptOutcomes(steps: AgentStep[]): TestOutcome[] {
  const observationByStep = new Map<number, AgentStep>();
  for (const step of steps) {
    if (step.type === "observation") observationByStep.set(step.step_number, step);
  }
  const outcomes: TestOutcome[] = [];
  for (const step of steps) {
    if (step.type !== "tool_call" || !step.tool_name || !RUN_TOOLS.has(step.tool_name)) continue;
    const args = (step.content.arguments as Record<string, unknown>) ?? {};
    const command = typeof args.command === "string" ? args.command : "";
    if (!TEST_COMMAND_PATTERN.test(command)) continue;
    const observation = observationByStep.get(step.step_number);
    if (!observation) {
      outcomes.push("pending");
      continue;
    }
    const content = observation.content;
    const passed = !("error" in content) && content.exit_code === 0 && content.timed_out !== true;
    outcomes.push(passed ? "passed" : "failed");
  }
  return outcomes;
}

/** A compact real timeline for the self-healing loop — "✗ ✗ ✓ (passing)" — or null when there
 * were no test attempts at all, so callers can skip the line entirely rather than show a hollow
 * one. */
export function testOutcomesLabel(outcomes: TestOutcome[]): string | null {
  if (outcomes.length === 0) return null;
  const marks = outcomes.map((o) => (o === "passed" ? "✓" : o === "failed" ? "✗" : "…")).join(" ");
  const last = outcomes[outcomes.length - 1];
  const state = last === "passed" ? "passing" : last === "pending" ? "running" : "still failing";
  return `${marks} (${state})`;
}

/** The most recent tool_call step that doesn't have a matching observation yet (same
 * step_number, by design — see buildToolCallArgsLookup) — i.e. what the agent is doing *right
 * now*. Null once every tool_call has been answered (nothing in flight, only "thinking" or
 * about to finish) so callers fall back to a generic "Working…". */
export function findInFlightToolCall(steps: AgentStep[]): AgentStep | null {
  const observedStepNumbers = new Set(steps.filter((s) => s.type === "observation").map((s) => s.step_number));
  let result: AgentStep | null = null;
  for (const step of steps) {
    if (step.type === "tool_call" && !observedStepNumbers.has(step.step_number)) result = step;
  }
  return result;
}

export const PLAN_PANEL_WIDTH = 70;

/** Lines for a bordered "KIRXIL PLAN" panel around the model's real plan text (verbs.ts's `plan`
 * instruction asks it to format as "PLAN" + numbered steps + an estimate) — a shared, pure,
 * testable piece so runOnce.ts's plain console.log rendering and ui/PlanPanel.tsx's Ink rendering
 * draw the exact same box around the exact same real text, never two renderers drifting apart. */
export function planPanelLines(planText: string, width: number = PLAN_PANEL_WIDTH): string[] {
  const header = "─ KIRXIL PLAN ";
  return [
    `┌${header}${"─".repeat(Math.max(0, width - header.length))}┐`,
    "",
    ...planText.split("\n"),
    "",
    `└${"─".repeat(width)}┘`,
  ];
}

/** `expand: true` (the REPL's `/expand` toggle) bypasses the cap entirely — the content beyond
 * MAX_OUTPUT_LINES was never printed at all otherwise, not just scrolled off-screen, so there's
 * real content to reveal here, not a cosmetic clamp. */
export function trimLines(lines: string[], expand = false): string[] {
  if (expand || lines.length <= MAX_OUTPUT_LINES) return lines;
  return [...lines.slice(0, MAX_OUTPUT_LINES), `… and ${lines.length - MAX_OUTPUT_LINES} more lines`];
}

export interface ApprovalPrompt {
  title: string;
  detail: string;
  riskLevel: string;
  /** CRITICAL isn't reachable by any host./code. tool today (APPROVAL_REQUIRED_LEVELS is
   * {HIGH, CRITICAL} but nothing in app/tools/ is registered above HIGH) — this still tells
   * the UI to ask for a typed "CONFIRM" rather than a single y/n keypress if that ever changes,
   * rather than silently treating a future CRITICAL tool the same as HIGH. */
  requireTypedConfirmation: boolean;
}

/**
 * What to show while a run is paused at status "waiting_approval" (app/agents/runner.py) — built
 * from the tool_call step already in hand (its summarizeToolCall rendering) plus the risk level
 * fetched from the execution itself (GET /tools/executions/{id}), same two pieces of information
 * the web app's Agents page shows for the same pause (apps/web/.../agents/page.tsx).
 */
export function describeApprovalPrompt(toolName: string, riskLevel: string, args: Record<string, unknown>): ApprovalPrompt {
  const normalized = riskLevel.toLowerCase();
  if (toolName.startsWith("hermes.")) {
    return {
      title: `UNMAPPED HERMES TOOL: ${toolName}`,
      // JSON escaping keeps control characters in remote arguments from changing the terminal.
      detail: `${riskLevel.toUpperCase()} risk — fallback classification. Allow once only.\n` +
        `Scope is remote and not verified by Krixil. Inspect the full request:\n${JSON.stringify(args, null, 2)}`,
      riskLevel: normalized,
      requireTypedConfirmation: normalized === "critical",
    };
  }
  return {
    title: summarizeToolCall(toolName, args),
    detail: `${riskLevel.toUpperCase()} risk — approve to run it for real, or reject to stop this goal.`,
    riskLevel: normalized,
    requireTypedConfirmation: normalized === "critical",
  };
}

/** tool_call and its own observation share one step_number by design (app/agents/runner.py) —
 * this lets a renderer look up "what arguments produced this observation" without needing the
 * caller to track index math itself. Used for host.edit_file/code.edit_file specifically, whose
 * observation alone (`{path, edited: true}`) doesn't carry the actual content changed — the real
 * before/after text only exists on the tool_call's own arguments. */
export function buildToolCallArgsLookup(steps: AgentStep[]): Map<number, Record<string, unknown>> {
  const lookup = new Map<number, Record<string, unknown>>();
  for (const step of steps) {
    if (step.type === "tool_call") {
      lookup.set(step.step_number, (step.content.arguments as Record<string, unknown>) ?? {});
    }
  }
  return lookup;
}

export function describeObservation(step: AgentStep, toolCallArgs?: Record<string, unknown>): ObservationSummary {
  const content = step.content;
  const toolName = step.tool_name;

  if (content.status === "pending_approval") return { summary: "Paused for approval", body: [], tone: "muted" };
  if (content.error) {
    const message = String(content.error);
    // A real BLOCK-tier outcome (app/tools/risk_rules.py) — never offered for approval at all,
    // worth a distinct summary from an ordinary tool failure. error_message's own real prefix
    // ("Blocked: ...") is what this checks, not a guess.
    const summary = message.startsWith("Blocked:") ? "🚫 Blocked" : "Error";
    return { summary, body: [message], tone: "error" };
  }

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

  if (toolName && EDIT_TOOLS.has(toolName)) {
    const oldString = typeof toolCallArgs?.old_string === "string" ? toolCallArgs.old_string : undefined;
    const newString = typeof toolCallArgs?.new_string === "string" ? toolCallArgs.new_string : undefined;
    // Real before/after content when the caller has it (buildToolCallArgsLookup) — not a real
    // line-diff algorithm (no LCS/alignment), just the two real blocks the edit actually used,
    // shown as -/+ the way a diff reads. Falls back to the old one-line "Edited" when the
    // arguments aren't available (e.g. a caller that hasn't wired the lookup through yet).
    if (oldString === undefined || newString === undefined) {
      return { summary: "Edited", body: [], tone: "success" };
    }
    const oldLines = oldString.split("\n");
    const newLines = newString.split("\n");
    const body = [...oldLines.map((l) => `- ${l}`), ...newLines.map((l) => `+ ${l}`)];
    return { summary: `Edited (+${newLines.length}/-${oldLines.length})`, body, tone: "success" };
  }

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

/** A real icon for a swarm child's actual current status (kirxil swarm — see api.ts's
 * SwarmRunDetail/AgentRunOut). No fabricated per-child "personality" state, just what the real
 * status string already is. */
export function swarmChildStatusIcon(status: string): string {
  switch (status) {
    case "completed":
      return "✓";
    case "failed":
      return "✗";
    case "waiting_approval":
      return "⏸";
    case "queued":
      return "⏳";
    case "cancelled":
    case "stopped":
      return "○";
    case "running":
      return "◉";
    default:
      return "○";
  }
}
