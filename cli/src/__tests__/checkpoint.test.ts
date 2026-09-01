import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execa } from "execa";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  autoCheckpoint,
  diffStatSinceCheckpoint,
  findLastCheckpoint,
  manualCheckpoint,
  parseShortstat,
  resetToBeforeCheckpoint,
  workingTreeChangeSummary,
} from "../checkpoint.js";

// Real `git`, a real temp repo, no mocking — checkpoint.ts is a thin wrapper around actual git
// commands, so the thing worth testing is that the real commands do what's claimed, the same way
// index.ts's own `git diff`/`git status` commands are trusted to just shell out for real.
describe("checkpoint (real git, temp repo)", () => {
  let dir: string;

  beforeEach(async () => {
    dir = mkdtempSync(join(tmpdir(), "kirxil-checkpoint-"));
    await execa("git", ["init", "-q"], { cwd: dir });
    await execa("git", ["config", "user.email", "test@kirxil.local"], { cwd: dir });
    await execa("git", ["config", "user.name", "Kirxil Test"], { cwd: dir });
    writeFileSync(join(dir, "a.txt"), "hello\n");
    await execa("git", ["add", "-A"], { cwd: dir });
    await execa("git", ["commit", "-q", "-m", "initial"], { cwd: dir });
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("manualCheckpoint refuses an empty working tree", async () => {
    const result = await manualCheckpoint(dir);
    expect(result).toEqual({ ok: false, reason: "Nothing to checkpoint — working tree is clean." });
  });

  it("manualCheckpoint commits real changes and findLastCheckpoint finds it", async () => {
    writeFileSync(join(dir, "a.txt"), "changed\n");
    const result = await manualCheckpoint(dir, "before risky edit");
    expect(result.ok).toBe(true);

    const found = await findLastCheckpoint(dir);
    expect(found).toBeTruthy();
    const log = await execa("git", ["log", "-1", "--format=%s"], { cwd: dir });
    expect(log.stdout).toBe("kirxil: checkpoint: before risky edit");
  });

  it("autoCheckpoint is a silent no-op outside a git repo", async () => {
    const outside = mkdtempSync(join(tmpdir(), "kirxil-not-a-repo-"));
    try {
      const hash = await autoCheckpoint(outside, "do something");
      expect(hash).toBeNull();
    } finally {
      rmSync(outside, { recursive: true, force: true });
    }
  });

  it("autoCheckpoint is a silent no-op on a clean tree", async () => {
    const hash = await autoCheckpoint(dir, "do something");
    expect(hash).toBeNull();
  });

  it("diffStatSinceCheckpoint reports the real change, and resetToBeforeCheckpoint reverts it", async () => {
    writeFileSync(join(dir, "a.txt"), "changed by the agent\n");
    writeFileSync(join(dir, "b.txt"), "new file\n");
    const hash = await autoCheckpoint(dir, "make some changes");
    expect(hash).toBeTruthy();

    // Simulate more direct, uncommitted edits happening after the checkpoint (host.write_file
    // doesn't commit per write) — diffStatSinceCheckpoint has to see these too, not just the
    // checkpoint commit's own contents.
    writeFileSync(join(dir, "a.txt"), "changed again, uncommitted\n");

    const checkpoint = await findLastCheckpoint(dir);
    expect(checkpoint).toBeTruthy();
    const stat = await diffStatSinceCheckpoint(dir, checkpoint!);
    expect(stat).toContain("a.txt");
    expect(stat).toContain("b.txt");

    const reset = await resetToBeforeCheckpoint(dir, checkpoint!);
    expect(reset).toEqual({ ok: true });

    const content = await execa("git", ["show", "HEAD:a.txt"], { cwd: dir });
    expect(content.stdout).toBe("hello");
    const status = await execa("git", ["status", "--porcelain"], { cwd: dir });
    expect(status.stdout).toBe("");
  });

  it("workingTreeChangeSummary reports real insertions/deletions against HEAD", async () => {
    writeFileSync(join(dir, "a.txt"), "hello\nworld\n");
    const summary = await workingTreeChangeSummary(dir);
    expect(summary.filesChanged).toBe(1);
    expect(summary.insertions).toBe(1);
    expect(summary.deletions).toBe(0);
  });

  it("workingTreeChangeSummary is all-zero on a clean tree", async () => {
    const summary = await workingTreeChangeSummary(dir);
    expect(summary).toEqual({ filesChanged: 0, insertions: 0, deletions: 0 });
  });

  it("workingTreeChangeSummary is all-zero outside a git repo", async () => {
    const outside = mkdtempSync(join(tmpdir(), "kirxil-not-a-repo-"));
    try {
      const summary = await workingTreeChangeSummary(outside);
      expect(summary).toEqual({ filesChanged: 0, insertions: 0, deletions: 0 });
    } finally {
      rmSync(outside, { recursive: true, force: true });
    }
  });
});

describe("parseShortstat", () => {
  it("parses a typical git --shortstat line", () => {
    expect(parseShortstat("2 files changed, 14 insertions(+), 3 deletions(-)")).toEqual({
      filesChanged: 2,
      insertions: 14,
      deletions: 3,
    });
  });

  it("parses insertions-only (no deletions line at all)", () => {
    expect(parseShortstat("1 file changed, 1 insertion(+)")).toEqual({
      filesChanged: 1,
      insertions: 1,
      deletions: 0,
    });
  });

  it("returns all zeros for empty input", () => {
    expect(parseShortstat("")).toEqual({ filesChanged: 0, insertions: 0, deletions: 0 });
  });
});
