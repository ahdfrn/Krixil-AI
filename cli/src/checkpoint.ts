/**
 * Checkpoint & Rollback (PRD §29, "Kesalahan harus dapat dipulihkan — Checkpoint first", §48) —
 * real `git` commits, not a custom undo log. host.write_file/host.run_command write straight to
 * disk with no approval gate of their own (see docs/architecture/coding-agent.md), so this is
 * the CLI's actual safety net: a checkpoint before each run means a bad run is always something
 * `kirxil undo` can get back out of, as long as the folder is a git repo. Best-effort everywhere
 * — a non-repo folder, a missing `git`, or a commit failure should never block the goal itself
 * from running, only mean there's nothing to undo to.
 */

import { execa } from "execa";

const CHECKPOINT_PREFIX = "kirxil: checkpoint";

export async function isGitRepo(cwd: string): Promise<boolean> {
  const result = await execa("git", ["rev-parse", "--is-inside-work-tree"], { cwd, reject: false });
  return !result.failed && result.stdout.trim() === "true";
}

async function hasStagedChanges(cwd: string): Promise<boolean> {
  const result = await execa("git", ["diff", "--cached", "--quiet"], { cwd, reject: false });
  // `git diff --quiet` exits 0 when there's nothing to show — "failed" here just means "found a
  // diff", not a real execa failure; reject:false is what lets us read that exit code at all.
  return result.exitCode !== 0;
}

/** Called right before an agent run starts. Silent no-op outside a git repo or when the tree is
 * already clean (so a string of goals in a row doesn't produce an empty commit per run) — returns
 * the short hash only when it actually committed something worth being able to undo. */
export async function autoCheckpoint(cwd: string, goal: string): Promise<string | null> {
  if (!(await isGitRepo(cwd))) return null;
  const add = await execa("git", ["add", "-A"], { cwd, reject: false });
  if (add.failed) return null;
  if (!(await hasStagedChanges(cwd))) return null;
  const shortGoal = goal.length > 72 ? `${goal.slice(0, 72)}…` : goal;
  const commit = await execa("git", ["commit", "-m", `${CHECKPOINT_PREFIX} before: ${shortGoal}`], {
    cwd,
    reject: false,
  });
  if (commit.failed) return null;
  const hash = await execa("git", ["rev-parse", "--short", "HEAD"], { cwd, reject: false });
  return hash.failed ? null : hash.stdout.trim();
}

export type ManualCheckpointResult = { ok: true; hash: string } | { ok: false; reason: string };

/** `kirxil checkpoint [message]` — the explicit, user-named version of the same snapshot. */
export async function manualCheckpoint(cwd: string, message?: string): Promise<ManualCheckpointResult> {
  if (!(await isGitRepo(cwd))) return { ok: false, reason: "Not a git repository — run `git init` first." };
  await execa("git", ["add", "-A"], { cwd, reject: false });
  if (!(await hasStagedChanges(cwd))) return { ok: false, reason: "Nothing to checkpoint — working tree is clean." };
  const label = message?.trim() || new Date().toISOString();
  const commit = await execa("git", ["commit", "-m", `${CHECKPOINT_PREFIX}: ${label}`], { cwd, reject: false });
  if (commit.failed) return { ok: false, reason: commit.stderr || "git commit failed." };
  const hash = await execa("git", ["rev-parse", "--short", "HEAD"], { cwd, reject: false });
  return hash.failed ? { ok: false, reason: "Committed, but couldn't read the new hash." } : { ok: true, hash: hash.stdout.trim() };
}

/** Most recent commit made by either checkpoint function above — never a commit the user (or
 * anything else) made themselves, so `kirxil undo` can only ever reset to kirxil's own snapshots. */
export async function findLastCheckpoint(cwd: string): Promise<string | null> {
  const result = await execa("git", ["log", "-1", `--grep=^${CHECKPOINT_PREFIX}`, "--format=%H"], {
    cwd,
    reject: false,
  });
  if (result.failed || !result.stdout.trim()) return null;
  return result.stdout.trim();
}

async function checkpointParent(cwd: string, checkpointHash: string): Promise<{ ok: true; ref: string } | { ok: false; reason: string }> {
  const parent = await execa("git", ["rev-parse", `${checkpointHash}^`], { cwd, reject: false });
  if (parent.failed) return { ok: false, reason: parent.stderr || "That checkpoint has no parent commit to return to." };
  return { ok: true, ref: parent.stdout.trim() };
}

/** What `kirxil undo` would discard — everything (working tree + index) different from right
 * before the checkpoint, so the confirmation prompt shows the real, full blast radius. */
export async function diffStatSinceCheckpoint(cwd: string, checkpointHash: string): Promise<string> {
  const parent = await checkpointParent(cwd, checkpointHash);
  if (!parent.ok) return "";
  const diff = await execa("git", ["diff", "--stat", parent.ref], { cwd, reject: false });
  return diff.stdout;
}

/** The actual, deliberately destructive step — `git reset --hard` to before the checkpoint.
 * Only ever called after a human has seen diffStatSinceCheckpoint's output and confirmed. */
export async function resetToBeforeCheckpoint(cwd: string, checkpointHash: string): Promise<{ ok: true } | { ok: false; reason: string }> {
  const parent = await checkpointParent(cwd, checkpointHash);
  if (!parent.ok) return parent;
  const result = await execa("git", ["reset", "--hard", parent.ref], { cwd, reject: false });
  return result.failed ? { ok: false, reason: result.stderr || "git reset failed." } : { ok: true };
}
