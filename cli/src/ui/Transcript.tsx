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
  trimLines,
  type Tone,
} from "../render.js";

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

export function StepView({ step, toolCallArgs }: { step: AgentStep; toolCallArgs?: Record<string, unknown> }) {
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
    return <ResultLines summary={summary} body={body} tone={tone} />;
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
        <Text color="yellow">Paused waiting on approval — resolve it from the web app&apos;s Agents page.</Text>
      )}
      {status === "failed" && <Text color="red">Failed.</Text>}
    </Box>
  );
}
