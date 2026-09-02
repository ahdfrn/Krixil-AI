/**
 * Renders an agent run's steps as a live terminal transcript — Ink components over the shared,
 * framework-free logic in ../render.ts, so the interactive REPL and `kirxil run`'s plain-text
 * output (runOnce.ts) stay identical, the same way apps/web/.../step-view.tsx and
 * cli-python/krixil_cli/render.py already read the same shape.
 */

import React from "react";
import { Box, Text } from "ink";
import type { AgentStep } from "../api.js";
import {
  buildToolCallArgsLookup,
  describeInFlightStep,
  describeObservation,
  findInFlightToolCall,
  summarizeToolCall,
  testAttemptOutcomes,
  testOutcomesLabel,
  trimLines,
  type Tone,
} from "../render.js";

const TONE_COLOR: Record<Tone, string> = { success: "green", error: "red", muted: "white" };

function ResultLines({ summary, body, tone, expanded }: { summary: string; body: string[]; tone: Tone; expanded: boolean }) {
  const shown = trimLines(body, expanded);
  return (
    <Box flexDirection="column" marginLeft={2}>
      <Text color={TONE_COLOR[tone]} dimColor={tone === "muted"}>
        ⎿ {summary}
      </Text>
      {shown.map((line, i) => (
        <Text key={i} dimColor>
          {"   " + line}
        </Text>
      ))}
    </Box>
  );
}

export function StepView({
  step,
  toolCallArgs,
  expanded = false,
}: {
  step: AgentStep;
  toolCallArgs?: Record<string, unknown>;
  expanded?: boolean;
}) {
  if (step.type === "tool_call") {
    return (
      <Text>
        <Text color="cyan" bold>
          ⏺{" "}
        </Text>
        {summarizeToolCall(step.tool_name, (step.content.arguments as Record<string, unknown>) ?? {})}
      </Text>
    );
  }
  if (step.type === "observation") {
    const { summary, body, tone } = describeObservation(step, toolCallArgs);
    return <ResultLines summary={summary} body={body} tone={tone} expanded={expanded} />;
  }
  // final_response
  return (
    <Box marginTop={1}>
      <Text>{String(step.content.content ?? "")}</Text>
    </Box>
  );
}

export function WorkingIndicator({
  elapsedSeconds,
  toolCalls,
  label,
}: {
  elapsedSeconds: number;
  toolCalls: number;
  label: string;
}) {
  return (
    <Text color="cyan">
      ● {label} ({elapsedSeconds}s · {toolCalls} tool calls) <Text dimColor>(Ctrl+C to stop)</Text>
    </Text>
  );
}

/** A real, terminal-state summary for one completed/failed run — tool-call count plus the
 * self-healing pass/fail sequence, both read straight from this run's own steps (never file-change
 * stats, which StatusBar already owns for the *current* run only: attributing a git diff to one
 * past run in a multi-turn REPL session would be dishonest once a later run has touched the same
 * working tree). Renders nothing for a plan run or a run with no tool calls at all — nothing
 * worth summarizing. */
export function RunSummary({ steps, status }: { steps: AgentStep[]; status: string }) {
  if (status !== "completed" && status !== "failed") return null;
  const toolCalls = steps.filter((s) => s.type === "tool_call").length;
  if (toolCalls === 0) return null;
  const testsLabel = testOutcomesLabel(testAttemptOutcomes(steps));
  const icon = status === "completed" ? "✓" : "✗";
  const color = status === "completed" ? "green" : "red";
  return (
    <Text dimColor>
      <Text color={color}>{icon}</Text> {toolCalls} tool call{toolCalls === 1 ? "" : "s"}
      {testsLabel ? ` · tests ${testsLabel}` : ""}
    </Text>
  );
}

export function Transcript({
  goal,
  steps,
  status,
  elapsedSeconds,
  expanded = false,
}: {
  goal: string;
  steps: AgentStep[];
  status: string;
  elapsedSeconds: number;
  /** Real content beyond MAX_OUTPUT_LINES was never printed at all, not just scrolled off — this
   * bypasses that cap for every observation in this transcript (toggled per-run via the REPL's
   * `/expand` command, App.tsx). */
  expanded?: boolean;
}) {
  const toolCallArgsByStep = buildToolCallArgsLookup(steps);
  const inFlight = findInFlightToolCall(steps);
  const workingLabel = (inFlight && describeInFlightStep(inFlight.tool_name, toolCallArgsByStep.get(inFlight.step_number) ?? {})) ?? "Working…";
  return (
    <Box flexDirection="column">
      <Text bold>› {goal}</Text>
      <Box height={1} />
      {steps.map((step, i) => (
        <StepView
          key={`${step.step_number}-${step.type}-${i}`}
          step={step}
          toolCallArgs={step.type === "observation" ? toolCallArgsByStep.get(step.step_number) : undefined}
          expanded={expanded}
        />
      ))}
      {status === "running" && (
        <WorkingIndicator
          elapsedSeconds={elapsedSeconds}
          toolCalls={steps.filter((s) => s.type === "tool_call").length}
          label={workingLabel}
        />
      )}
      {status === "cancelled" && <Text dimColor>Stopped.</Text>}
      {status === "waiting_approval" && (
        // The interactive REPL (App.tsx) and `kirxil run` (runOnce.ts) both already resolve
        // approvals themselves — this only covers the brief gap before their own confirm panel/
        // prompt takes over, so it must never claim the web app is where to go instead.
        <Text color="yellow">Waiting for approval…</Text>
      )}
      {status === "failed" && <Text color="red">Failed.</Text>}
    </Box>
  );
}
