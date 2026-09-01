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
  const rootLabel = root === "workspace" ? "Workspace" : "Local";
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

export interface CodeStats {
  sessions: number;
  totalRuns: number;
  totalToolCalls: number;
  activeDays: number;
  currentStreak: number;
  longestStreak: number;
  peakHour: number | null;
  favoriteRoot: CodeRoot | null;
  /** "YYYY-MM-DD" -> run count that day, local time — feeds the activity heatmap. */
  activityByDate: Map<string, number>;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function dateKey(iso: string): string {
  const d = new Date(iso);
  // Local calendar date, not the ISO string's own (UTC) date — a run at 11pm local time
  // shouldn't count against the next UTC day.
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Every number here is derived from real run history — no fabricated demo data. Only counts
 * runs that actually came from the Code page (parseCodeGoal), same scoping deriveCodeSessions
 * already uses, so a Chat/Deep-Research run elsewhere doesn't skew "your coding activity". */
export function computeCodeStats(runs: AgentRunOut[]): CodeStats {
  const codeRuns = runs.filter((r) => parseCodeGoal(r.goal) !== null);

  const activityByDate = new Map<string, number>();
  const hourCounts = new Map<number, number>();
  const rootCounts = new Map<CodeRoot, number>();
  let totalToolCalls = 0;

  for (const run of codeRuns) {
    const created = new Date(run.created_at);
    const key = dateKey(run.created_at);
    activityByDate.set(key, (activityByDate.get(key) ?? 0) + 1);
    hourCounts.set(created.getHours(), (hourCounts.get(created.getHours()) ?? 0) + 1);
    totalToolCalls += run.tool_call_count;
    const parsed = parseCodeGoal(run.goal);
    if (parsed) rootCounts.set(parsed.root, (rootCounts.get(parsed.root) ?? 0) + 1);
  }

  const sortedDates = [...activityByDate.keys()].sort();
  let longestStreak = 0;
  let running = 0;
  let prevTime: number | null = null;
  for (const key of sortedDates) {
    const t = new Date(key).getTime();
    running = prevTime !== null && t - prevTime === DAY_MS ? running + 1 : 1;
    longestStreak = Math.max(longestStreak, running);
    prevTime = t;
  }

  let currentStreak = 0;
  if (sortedDates.length > 0) {
    const last = sortedDates[sortedDates.length - 1];
    const today = dateKey(new Date().toISOString());
    const yesterday = dateKey(new Date(Date.now() - DAY_MS).toISOString());
    if (last === today || last === yesterday) {
      currentStreak = 1;
      for (let i = sortedDates.length - 1; i > 0; i--) {
        const gap = new Date(sortedDates[i]).getTime() - new Date(sortedDates[i - 1]).getTime();
        if (gap === DAY_MS) currentStreak += 1;
        else break;
      }
    }
  }

  const peakHour = [...hourCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  const favoriteRoot = [...rootCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;

  return {
    sessions: deriveCodeSessions(codeRuns).length,
    totalRuns: codeRuns.length,
    totalToolCalls,
    activeDays: activityByDate.size,
    currentStreak,
    longestStreak,
    peakHour,
    favoriteRoot,
    activityByDate,
  };
}

export function formatPeakHour(hour: number): string {
  const period = hour >= 12 ? "PM" : "AM";
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${h12} ${period}`;
}
