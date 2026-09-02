import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { formatVerifyResultLines, runVerifyPipeline, type VerifyResult } from "../verify.js";

// Real subprocesses, real exit codes — same discipline checkpoint.test.ts already uses for real
// git commands: the thing worth testing is that runVerifyPipeline's real behavior (stop at first
// real failure) matches what it claims, not a mocked stand-in for execa.
describe("runVerifyPipeline (real subprocesses)", () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "kirxil-verify-"));
    writeFileSync(join(dir, "pass.js"), "process.exit(0);\n");
    writeFileSync(join(dir, "fail.js"), 'console.error("boom"); process.exit(1);\n');
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("runs every command and reports allPassed when they all succeed", async () => {
    const result = await runVerifyPipeline(["node pass.js", "node pass.js"], dir);
    expect(result.allPassed).toBe(true);
    expect(result.stoppedEarly).toBe(false);
    expect(result.steps).toHaveLength(2);
    expect(result.steps.every((s) => s.ok)).toBe(true);
  });

  it("stops at the first real failure and never runs the remaining commands", async () => {
    const result = await runVerifyPipeline(["node pass.js", "node fail.js", "node pass.js"], dir);
    expect(result.allPassed).toBe(false);
    expect(result.stoppedEarly).toBe(true);
    expect(result.steps).toHaveLength(2);
    expect(result.steps[0]!.ok).toBe(true);
    expect(result.steps[1]!.ok).toBe(false);
    expect(result.steps[1]!.exitCode).toBe(1);
    expect(result.steps[1]!.stderr).toContain("boom");
  });

  it("stoppedEarly is false when the failure is the last configured command", async () => {
    const result = await runVerifyPipeline(["node pass.js", "node fail.js"], dir);
    expect(result.allPassed).toBe(false);
    expect(result.stoppedEarly).toBe(false);
    expect(result.steps).toHaveLength(2);
  });

  it("returns an empty passing result for an empty command list", async () => {
    const result = await runVerifyPipeline([], dir);
    expect(result).toEqual({ steps: [], allPassed: true, stoppedEarly: false });
  });
});

describe("formatVerifyResultLines", () => {
  it("summarizes an all-passed result", () => {
    const result: VerifyResult = {
      steps: [
        { command: "npm run typecheck", exitCode: 0, stdout: "", stderr: "", ok: true },
        { command: "npm test", exitCode: 0, stdout: "", stderr: "", ok: true },
      ],
      allPassed: true,
      stoppedEarly: false,
    };
    const lines = formatVerifyResultLines(result);
    expect(lines.some((l) => l.includes("✓ [1] npm run typecheck"))).toBe(true);
    expect(lines.some((l) => l.includes("✓ [2] npm test"))).toBe(true);
    expect(lines.some((l) => l.includes("All 2 verification steps passed"))).toBe(true);
  });

  it("shows the real failure output and exit code, and names the remaining steps as not run", () => {
    const result: VerifyResult = {
      steps: [
        { command: "npm run typecheck", exitCode: 0, stdout: "", stderr: "", ok: true },
        { command: "npm test", exitCode: 1, stdout: "", stderr: "2 tests failed", ok: false },
      ],
      allPassed: false,
      stoppedEarly: true,
    };
    const lines = formatVerifyResultLines(result);
    expect(lines.some((l) => l.includes("✗ [2] npm test (exit 1)"))).toBe(true);
    expect(lines.some((l) => l.includes("2 tests failed"))).toBe(true);
    expect(lines.some((l) => l.includes('"npm test" failed'))).toBe(true);
    expect(lines.some((l) => l.includes("Remaining steps were not run"))).toBe(true);
  });
});
