"use client";

import { Sparkles, Terminal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ActivityHeatmap } from "@/components/agent-run/activity-heatmap";
import { CopyableCommand } from "@/components/ui/copyable-command";
import { listAgentRuns, type AgentRunOut } from "@/lib/api/agents";
import { computeCodeStats, formatPeakHour } from "@/lib/utils/code-sessions";
import { useAuthStore } from "@/stores/auth-store";

// The Code page used to run goals directly (a full agent-run composer + live transcript). Moved
// to a real, dedicated terminal client instead — see cli/README.md — so this page's job changed
// from "run goals" to "help you get the CLI running," per the user's explicit request once that
// CLI existed: "code ini aja hapus atau rubah jadikan tempat untuk mengakses CLI nya dari sini."
// The stats/heatmap below are untouched — they're about real coding-agent activity regardless of
// which client (web, historically, or the CLI now) produced it, still computed the same way.
export default function CodePage() {
  const user = useAuthStore((s) => s.user);
  const [allRuns, setAllRuns] = useState<AgentRunOut[]>([]);

  useEffect(() => {
    listAgentRuns()
      .then(setAllRuns)
      .catch(() => {
        // Not worth surfacing — the page still works fine starting blank.
      });
  }, []);

  const stats = useMemo(() => computeCodeStats(allRuns), [allRuns]);
  const displayName = user?.email.split("@")[0] ?? "there";

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="flex h-12 shrink-0 items-center border-b border-border px-4">
        <h1 className="text-sm font-medium">Code</h1>
      </header>

      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 pt-6 pb-10 sm:pt-10">
          <div className="flex items-center gap-3">
            <Sparkles className="size-7 shrink-0 text-primary" />
            <h2 className="text-2xl font-semibold sm:text-3xl">Hey {displayName}, run it from your terminal</h2>
          </div>

          {stats.totalRuns > 0 && (
            <div className="rounded-2xl border border-border bg-secondary/10 p-5">
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                <StatTile label="Sessions" value={String(stats.sessions)} />
                <StatTile label="Runs" value={String(stats.totalRuns)} />
                <StatTile label="Tool calls" value={String(stats.totalToolCalls)} />
                <StatTile label="Active days" value={String(stats.activeDays)} />
                <StatTile label="Current streak" value={`${stats.currentStreak}d`} />
                <StatTile label="Longest streak" value={`${stats.longestStreak}d`} />
                <StatTile
                  label="Peak hour"
                  value={stats.peakHour === null ? "—" : formatPeakHour(stats.peakHour)}
                />
              </div>
              <div className="mt-4 flex items-center gap-1 overflow-x-auto pb-1">
                <ActivityHeatmap activityByDate={stats.activityByDate} />
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-border p-5">
            <div className="flex items-center gap-2">
              <Terminal className="size-4 text-primary" />
              <h3 className="text-sm font-semibold">krixil — the coding agent, in your terminal</h3>
            </div>
            <p className="mt-1.5 text-sm text-muted-foreground">
              Same tools, same live <code className="font-mono text-xs">⏺</code>/
              <code className="font-mono text-xs">⎿</code> transcript, same real, unsandboxed
              access to whatever folder you launch it from — no isolation. Reading and writing
              files runs immediately; running a shell command pauses and asks you to approve it
              first (high risk). Requires <code className="font-mono text-xs">host-runner</code>{" "}
              running locally (see{" "}
              <code className="font-mono text-xs">services/host-runner/README.md</code>).
            </p>

            <div className="mt-4 flex flex-col gap-3">
              <Step n={1} label="Install (one time)">
                <CopyableCommand command={"cd cli\nnpm install\nnpm run build\nnpm link"} />
              </Step>
              <Step n={2} label="Log in (one time)">
                <CopyableCommand command="kirxil login" />
                <p className="mt-1 text-xs text-muted-foreground">
                  Asks for your workspace slug, email, password, and your real{" "}
                  <code className="font-mono">HOST_ROOT</code> (e.g. <code className="font-mono">D:\</code>).
                </p>
              </Step>
              <Step n={3} label="Use it">
                <CopyableCommand command={"cd D:\\some\\real\\project\nkirxil"} />
                <p className="mt-1 text-xs text-muted-foreground">
                  Drops into an interactive prompt, scoped to whichever folder you launched it
                  from. <code className="font-mono">Ctrl+C</code> stops a run in progress,{" "}
                  <code className="font-mono">/model</code> switches models,{" "}
                  <code className="font-mono">kirxil run &quot;&lt;goal&gt;&quot;</code> runs one
                  goal non-interactively.
                </p>
              </Step>
            </div>
            <p className="mt-4 text-xs text-muted-foreground">
              Full walkthrough, troubleshooting, and how to run every part of Krixil: see{" "}
              <a href="/help" className="text-foreground underline underline-offset-2">
                Help
              </a>
              .
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-background px-3.5 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function Step({ n, label, children }: { n: number; label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="flex size-5 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium">
        {n}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <div className="mt-1">{children}</div>
      </div>
    </div>
  );
}
