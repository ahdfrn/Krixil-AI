import type { AgentRunOut } from "@/lib/api/agents";

export type CodeRoot = "workspace" | "host";

// Every goal the Code page builds (buildCodeGoal, apps/web/.../code/page.tsx) starts with this
// exact phrase and follows one of two fixed shapes — used here to recognize "a run that came from
// the Code page" among every run in the tenant's whole Agents history (which also includes Deep
// Research runs, etc.), and to parse back out which (root, folder) it belongs to. There's no
// backend "session" concept to query instead — a session is purely this derived (root, dir) pair.
const GOAL_PREFIX = "Using your";
const TASK_MARKER = "Task: ";
const DIR_RE = /work within the "([^"]+)" folder/;

export interface ParsedCodeGoal {
  root: CodeRoot;
  dir: string;
  instruction: string;
}

export function parseCodeGoal(goal: string): ParsedCodeGoal | null {
  if (!goal.startsWith(GOAL_PREFIX)) return null;

  const root: CodeRoot | null = goal.includes("host.list_files")
    ? "host"
    : goal.includes("code.list_files")
      ? "workspace"
      : null;
  if (root === null) return null;

  const dirMatch = DIR_RE.exec(goal);
  const dir = dirMatch ? dirMatch[1] : ".";

  const taskIdx = goal.indexOf(TASK_MARKER);
  const instruction = taskIdx === -1 ? goal : goal.slice(taskIdx + TASK_MARKER.length);

  return { root, dir, instruction };
}

export interface CodeSession {
  root: CodeRoot;
  dir: string;
  label: string;
  updatedAt: string;
}

function sessionLabel(root: CodeRoot, dir: string): string {
  const rootLabel = root === "workspace" ? "Workspace" : "This Computer";
  return dir === "." ? rootLabel : `${rootLabel} / ${dir}`;
}

/** One entry per distinct (root, folder) a Code-page goal has actually run in, newest activity
 * first — there's no stored "session" row anywhere; this is derived fresh from the run list every
 * time (see app/agents/router.py's GET /agents, already fetched for the history-restore effect). */
export function deriveCodeSessions(runs: AgentRunOut[]): CodeSession[] {
  const byKey = new Map<string, CodeSession>();
  for (const run of runs) {
    const parsed = parseCodeGoal(run.goal);
    if (!parsed) continue;
    const key = `${parsed.root}:${parsed.dir}`;
    const existing = byKey.get(key);
    if (!existing || new Date(run.created_at) > new Date(existing.updatedAt)) {
      byKey.set(key, {
        root: parsed.root,
        dir: parsed.dir,
        label: sessionLabel(parsed.root, parsed.dir),
        updatedAt: run.created_at,
      });
    }
  }
  return [...byKey.values()].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}
