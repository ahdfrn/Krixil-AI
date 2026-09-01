/**
 * Renders an agent run's steps as a live terminal transcript — Ink components over the shared,
 * framework-free logic in ../render.ts, so the interactive REPL and `kirxil run`'s plain-text
 * output (runOnce.ts) stay identical, the same way apps/web/.../step-view.tsx and
 * cli-python/krixil_cli/render.py already read the same shape.
 */

import React from "react";
import { Box, Text } from "ink";
import type { AgentStep } from "../api.js";
import { describeObservation, summarizeToolCall, trimLines, type Tone } from "../render.js";

const TONE_COLOR: Record<Tone, string> = { success: "green", error: "red", muted: "white" };

function ResultLines({ summary, body, tone }: { summary: string; body: string[]; tone: Tone }) {
  return (
    <Box flexDirection="column" marginLeft={2}>
      <Text color={TONE_COLOR[tone]} dimColor={tone === "muted"}>
        ⎿ {summary}
      </Text>
      {trimLines(body).map((line, i) => (
        <Text key={i} dimColor>
          {"   " + line}
        </Text>
      ))}
    </Box>
  );
}

export function StepView({ step }: { step: AgentStep }) {
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
    const { summary, body, tone } = describeObservation(step);
    return <ResultLines summary={summary} body={body} tone={tone} />;
  }
  // final_response
  return (
    <Box marginTop={1}>
      <Text>{String(step.content.content ?? "")}</Text>
    </Box>
  );
}

export function WorkingIndicator({ elapsedSeconds, toolCalls }: { elapsedSeconds: number; toolCalls: number }) {
  return (
    <Text color="cyan">
      ● Working… ({elapsedSeconds}s · {toolCalls} tool calls) <Text dimColor>(Ctrl+C to stop)</Text>
    </Text>
  );
}

export function Transcript({
  goal,
  steps,
  status,
  elapsedSeconds,
}: {
  goal: string;
  steps: AgentStep[];
  status: string;
  elapsedSeconds: number;
}) {
  return (
    <Box flexDirection="column">
      <Text bold>› {goal}</Text>
      <Box height={1} />
      {steps.map((step, i) => (
        <StepView key={`${step.step_number}-${step.type}-${i}`} step={step} />
      ))}
      {status === "running" && (
        <WorkingIndicator elapsedSeconds={elapsedSeconds} toolCalls={steps.filter((s) => s.type === "tool_call").length} />
      )}
      {status === "cancelled" && <Text dimColor>Stopped.</Text>}
      {status === "waiting_approval" && (
        <Text color="yellow">Paused waiting on approval — resolve it from the web app&apos;s Agents page.</Text>
      )}
      {status === "failed" && <Text color="red">Failed.</Text>}
    </Box>
  );
}
