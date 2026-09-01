/**
 * `kirxil run "<goal>"` — one-shot, non-interactive. Plain console.log rather than Ink: this
 * needs to behave correctly when piped/redirected (scripting is the whole point of this command),
 * and Ink's raw-mode terminal takeover assumes a real interactive TTY.
 */

import { ApiError, KrixilApi, type AgentRun } from "./api.js";
import { autoCheckpoint } from "./checkpoint.js";
import { buildGoal } from "./goal.js";
import { confirm } from "./prompt.js";
import { describeApprovalPrompt, describeObservation, summarizeToolCall, trimLines } from "./render.js";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Blocks on a real y/n prompt for a paused HIGH/CRITICAL-risk tool call — see
 * app/tools/base.py's APPROVAL_REQUIRED_LEVELS. Approving lets the agent run resume and keep
 * working (app/tools/service.py's approve_execution schedules that server-side); rejecting stops
 * the run for good. Either way the caller's next status poll picks up what actually happened —
 * this doesn't guess at the outcome, just asks and submits the answer. */
async function handleApproval(api: KrixilApi, executionId: string): Promise<void> {
  let execution;
  try {
    execution = await api.getExecution(executionId);
  } catch (err) {
    console.error(err instanceof ApiError ? `Couldn't load the pending action: ${err.detail}` : "Couldn't load the pending action.");
    return;
  }
  const { title, detail } = describeApprovalPrompt(execution.tool_name, execution.risk_level, execution.input);
  console.log(`\n⏸ ${title}`);
  console.log(`  ${detail}`);
  const approved = await confirm("Approve?");
  try {
    if (approved) {
      await api.approveExecution(executionId);
    } else {
      await api.rejectExecution(executionId, "rejected from kirxil run");
      console.log("Rejected — stopping this goal.");
    }
  } catch (err) {
    console.error(err instanceof ApiError ? err.detail : "Couldn't submit that decision.");
  }
}

function printStep(step: AgentRun["steps"][number]): void {
  if (step.type === "tool_call") {
    console.log(`⏺ ${summarizeToolCall(step.tool_name, (step.content.arguments as Record<string, unknown>) ?? {})}`);
    return;
  }
  if (step.type === "observation") {
    const { summary, body } = describeObservation(step);
    console.log(`  ⎿ ${summary}`);
    for (const line of trimLines(body)) console.log(`     ${line}`);
    return;
  }
  console.log("");
  console.log(String(step.content.content ?? ""));
}

export async function runGoalOnce(
  api: KrixilApi,
  instruction: string,
  dir: string,
  model: string,
  maxSteps?: number,
): Promise<void> {
  const goalText = buildGoal(instruction, dir);
  console.log(`› ${instruction}\n`);

  // Best-effort, silent outside a git repo or on a clean tree (see cli/src/checkpoint.ts) — this
  // is what makes `kirxil undo` mean something after a goal like this one, without needing the
  // agent loop itself to know anything about checkpoints.
  const checkpointHash = await autoCheckpoint(process.cwd(), instruction);
  if (checkpointHash) console.log(`📍 Checkpointed ${checkpointHash} — \`kirxil undo\` can get back to this.\n`);

  let started;
  try {
    started = await api.runAgent(goalText, model, maxSteps);
  } catch (err) {
    console.error(err instanceof ApiError ? `Couldn't start that run: ${err.detail}` : "Couldn't start that run.");
    process.exitCode = 1;
    return;
  }

  let printed = 0;
  let run: AgentRun = { ...started, steps: [] };
  const onSigint = () => {
    void api.cancel(run.id);
  };
  process.on("SIGINT", onSigint);

  try {
    for (;;) {
      try {
        run = await api.getStatus(run.id);
      } catch (err) {
        console.error(err instanceof ApiError ? `Lost track of that run: ${err.detail}` : "Lost track of that run.");
        break;
      }
      for (; printed < run.steps.length; printed++) printStep(run.steps[printed]!);
      if (run.status === "waiting_approval" && run.pending_execution_id) {
        await handleApproval(api, run.pending_execution_id);
        continue;
      }
      if (run.status !== "running") break;
      await sleep(1000);
    }
  } finally {
    process.off("SIGINT", onSigint);
  }

  console.log("");
  if (run.status === "cancelled") console.log("Stopped.");
  if (run.error_message) console.error(run.error_message);
  process.exitCode = run.status === "failed" ? 1 : 0;
}
