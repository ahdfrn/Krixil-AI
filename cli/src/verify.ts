/**
 * Real, deterministic verification pipeline — `.kirxil.yml`'s `verify:` list, run for real in
 * order via execaCommand (real CLI-native execution, same as checkpoint.ts/doctor — not routed
 * through host.run_command/the agent, since these are commands the user themselves configured and
 * already trusts). Stops at the first real non-zero exit, same "no fabricated ✓ Done" reasoning
 * PRD §13's Verification Engine describes: a real pass/fail per real command, not a model's own
 * narrated claim that everything's fine.
 */
import { execaCommand } from "execa";

export interface VerifyStepResult {
  command: string;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  ok: boolean;
}

export interface VerifyResult {
  steps: VerifyStepResult[];
  allPassed: boolean;
  // true when a failure stopped the pipeline before every configured command ran — distinguishes
  // "3 of 4 configured commands ran, the 3rd failed" from "all 4 ran and all 4 passed".
  stoppedEarly: boolean;
}

/** Shared between `kirxil verify` (index.ts), `kirxil build`'s automatic tail (runOnce.ts), and
 * the interactive REPL's build handoff (ui/App.tsx) — one real rendering of the same real result,
 * not three copies drifting apart. */
export function formatVerifyResultLines(result: VerifyResult): string[] {
  const lines: string[] = [];
  for (const [i, step] of result.steps.entries()) {
    const icon = step.ok ? "✓" : "✗";
    lines.push(`${icon} [${i + 1}] ${step.command}${step.ok ? "" : ` (exit ${step.exitCode ?? "?"})`}`);
    if (!step.ok) {
      const output = (step.stderr || step.stdout).trim();
      if (output) for (const line of output.split("\n").slice(0, 20)) lines.push(`    ${line}`);
    }
  }
  if (result.allPassed) {
    lines.push(`\nAll ${result.steps.length} verification step${result.steps.length === 1 ? "" : "s"} passed.`);
  } else {
    lines.push(
      `\nStopped after ${result.steps.length} step${result.steps.length === 1 ? "" : "s"} — ` +
        `"${result.steps[result.steps.length - 1]!.command}" failed.` +
        (result.stoppedEarly ? " Remaining steps were not run." : ""),
    );
  }
  return lines;
}

export function printVerifyResult(result: VerifyResult): void {
  for (const line of formatVerifyResultLines(result)) console.log(line);
}

export async function runVerifyPipeline(commands: string[], cwd: string): Promise<VerifyResult> {
  const steps: VerifyStepResult[] = [];
  for (const command of commands) {
    const result = await execaCommand(command, { cwd, reject: false });
    const ok = result.exitCode === 0;
    steps.push({
      command,
      exitCode: result.exitCode ?? null,
      stdout: result.stdout,
      stderr: result.stderr,
      ok,
    });
    if (!ok) {
      return { steps, allPassed: false, stoppedEarly: steps.length < commands.length };
    }
  }
  return { steps, allPassed: true, stoppedEarly: false };
}
