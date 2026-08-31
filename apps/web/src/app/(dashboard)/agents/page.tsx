"use client";

import { Bot, Check, Loader2, Search, TriangleAlert, Wrench, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { MarkdownContent } from "@/components/chat/markdown-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  getAgentRunStatus,
  listAgentRuns,
  runAgent,
  type AgentRunDetailOut,
  type AgentRunOut,
  type AgentRunStatus,
  type AgentStepOut,
} from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import { approveExecution, rejectExecution } from "@/lib/api/tools";

const STATUS_VARIANT: Record<AgentRunStatus, "secondary" | "outline" | "destructive"> = {
  running: "outline",
  completed: "secondary",
  stopped: "outline",
  waiting_approval: "destructive",
  failed: "destructive",
};

type AgentMode = "quick" | "research";

const MODE_COPY: Record<AgentMode, { label: string; placeholder: string; buttonLabel: string }> = {
  quick: {
    label: "What should the agent do?",
    placeholder: "e.g. Find out how many documents I've uploaded and summarize what they cover.",
    buttonLabel: "Run agent",
  },
  research: {
    label: "What do you want to research?",
    placeholder: "e.g. What are the latest developments in solid-state batteries?",
    buttonLabel: "Research",
  },
};

// Wraps a plain research question into a goal that nudges the agent toward the shape Deep
// Research implies — multiple searches, cross-referenced, written up as a report — using only
// the existing goal-driven Agent loop and web.search tool. No backend change: this is entirely a
// framing of the same POST /agents/run this page already calls for "quick" mode.
function buildResearchGoal(question: string): string {
  return (
    "Research the following topic using web search. If one search isn't enough, search again " +
    "from a different angle and cross-reference what you find. Then write a clear, organized " +
    `report: a short summary followed by key findings, citing your sources.\n\nTopic: ${question}`
  );
}

export default function AgentsPage() {
  const [runs, setRuns] = useState<AgentRunOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [mode, setMode] = useState<AgentMode>("quick");
  const [goal, setGoal] = useState("");
  const [isRunning, setIsRunning] = useState(false);

  const [selectedRun, setSelectedRun] = useState<AgentRunDetailOut | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [approvalAction, setApprovalAction] = useState<string | null>(null);

  async function loadRuns() {
    setIsLoading(true);
    try {
      setRuns(await listAgentRuns());
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't load agent runs.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // Fetch-on-mount, same pattern as the rest of this app's data loading (chat-store.ts).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadRuns();
  }, []);

  async function openRun(id: string) {
    setIsLoadingDetail(true);
    setSelectedRun(null);
    try {
      setSelectedRun(await getAgentRunStatus(id));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't load that run.");
    } finally {
      setIsLoadingDetail(false);
    }
  }

  async function handleRun(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = goal.trim();
    if (!trimmed) return;
    setIsRunning(true);
    try {
      const run = await runAgent(mode === "research" ? buildResearchGoal(trimmed) : trimmed);
      setRuns((prev) => [run, ...prev]);
      setGoal("");
      void openRun(run.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "That run failed to start.");
    } finally {
      setIsRunning(false);
    }
  }

  async function handleApprove(executionId: string) {
    setApprovalAction(executionId);
    try {
      const updated = await approveExecution(executionId);
      if (updated.status === "completed") {
        toast.success("Approved — the tool ran successfully.");
      } else {
        toast.error(updated.error_message ?? "Approved, but the tool failed to run.");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't approve that execution.");
    } finally {
      setApprovalAction(null);
    }
  }

  async function handleReject(executionId: string) {
    setApprovalAction(executionId);
    try {
      await rejectExecution(executionId);
      toast.info("Rejected.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't reject that execution.");
    } finally {
      setApprovalAction(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="flex h-12 shrink-0 items-center border-b border-border px-4">
        <h1 className="text-sm font-medium">Agents</h1>
      </header>

      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
          <form onSubmit={handleRun} className="flex flex-col gap-2 rounded-xl border border-border p-4">
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="agent-goal" className="text-xs font-medium text-muted-foreground">
                {MODE_COPY[mode].label}
              </label>
              <div className="flex rounded-md border border-border p-0.5">
                {(["quick", "research"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    disabled={isRunning}
                    onClick={() => setMode(m)}
                    className={cn(
                      "flex items-center gap-1 rounded-[5px] px-2 py-1 text-xs font-medium",
                      mode === m
                        ? "bg-secondary text-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {m === "quick" ? <Bot className="size-3.5" /> : <Search className="size-3.5" />}
                    {m === "quick" ? "Quick task" : "Deep research"}
                  </button>
                ))}
              </div>
            </div>
            <Textarea
              id="agent-goal"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder={MODE_COPY[mode].placeholder}
              rows={3}
              disabled={isRunning}
            />
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                {isRunning
                  ? "Running — this can take up to two minutes."
                  : mode === "research"
                    ? "Searches the web (possibly more than once), then writes up a report with sources."
                    : "Runs a full planner/executor loop within a fixed step and time budget."}
              </p>
              <Button type="submit" size="sm" disabled={isRunning || !goal.trim()} className="shrink-0">
                {isRunning ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : mode === "research" ? (
                  <Search className="size-3.5" />
                ) : (
                  <Bot className="size-3.5" />
                )}
                {MODE_COPY[mode].buttonLabel}
              </Button>
            </div>
          </form>

          <div className="flex flex-col gap-3">
            <h2 className="text-xs font-medium text-muted-foreground">Past runs</h2>
            {isLoading ? (
              <div className="flex flex-col gap-2">
                {Array.from({ length: 2 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            ) : runs.length === 0 ? (
              <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center">
                <Bot className="size-6 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">No agent runs yet — give it a goal above.</p>
              </div>
            ) : (
              runs.map((run) => (
                <button
                  key={run.id}
                  type="button"
                  onClick={() => void openRun(run.id)}
                  className="rounded-lg border border-border p-3 text-left text-sm hover:bg-accent"
                >
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate font-medium">{run.goal}</span>
                    <Badge variant={STATUS_VARIANT[run.status]}>{run.status.replace("_", " ")}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {run.step_count}/{run.max_steps} steps · {run.tool_call_count}/{run.max_tool_calls} tool calls ·{" "}
                    {new Date(run.created_at).toLocaleString()}
                  </p>
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      <Dialog open={!!selectedRun || isLoadingDetail} onOpenChange={(open) => !open && setSelectedRun(null)}>
        <DialogContent className="max-w-xl">
          {isLoadingDetail || !selectedRun ? (
            <div className="flex flex-col gap-2 py-4">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : (
            <RunDetail
              run={selectedRun}
              pendingApprovalId={approvalAction}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RunDetail({
  run,
  pendingApprovalId,
  onApprove,
  onReject,
}: {
  run: AgentRunDetailOut;
  pendingApprovalId: string | null;
  onApprove: (executionId: string) => void;
  onReject: (executionId: string) => void;
}) {
  return (
    <>
      <DialogHeader>
        <DialogTitle className="pr-6">{run.goal}</DialogTitle>
        <DialogDescription>
          {run.step_count}/{run.max_steps} steps · {run.tool_call_count}/{run.max_tool_calls} tool calls
        </DialogDescription>
      </DialogHeader>

      <div className="scrollbar-thin flex max-h-[60vh] flex-col gap-2 overflow-y-auto">
        {run.steps.map((step) => (
          // step_number is the loop iteration, not a unique row id — a tool_call and its
          // observation share one iteration's number, so the pair needs to be part of the key.
          <StepView key={`${step.step_number}-${step.type}`} step={step} />
        ))}

        {run.status === "waiting_approval" && run.pending_execution_id && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
            <div className="flex items-center gap-2 text-destructive">
              <TriangleAlert className="size-3.5 shrink-0" />
              <span className="font-medium">Waiting on your approval</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Approving or rejecting the tool call below will not continue this run — Krixil doesn&apos;t
              resume a paused run automatically. Start a new run afterward if you want it to keep going.
            </p>
            <div className="mt-2 flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={pendingApprovalId === run.pending_execution_id}
                onClick={() => onApprove(run.pending_execution_id!)}
              >
                {pendingApprovalId === run.pending_execution_id ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Check className="size-3.5" />
                )}
                Approve
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={pendingApprovalId === run.pending_execution_id}
                onClick={() => onReject(run.pending_execution_id!)}
              >
                <X className="size-3.5" />
                Reject
              </Button>
            </div>
          </div>
        )}

        {run.status === "failed" && run.error_message && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
            {run.error_message}
          </p>
        )}
      </div>
    </>
  );
}

function StepView({ step }: { step: AgentStepOut }) {
  if (step.type === "tool_call") {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-border bg-secondary/30 p-2.5 text-xs">
        <Wrench className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
        <div className="min-w-0">
          <span className="font-medium">Called {step.tool_name}</span>
          <pre className="mt-1 overflow-x-auto text-muted-foreground">
            {JSON.stringify(step.content.arguments, null, 2)}
          </pre>
        </div>
      </div>
    );
  }

  if (step.type === "observation") {
    const isPending = step.content.status === "pending_approval";
    const isError = "error" in step.content;
    return (
      <div
        className={`rounded-lg border p-2.5 text-xs ${
          isError ? "border-destructive/30 bg-destructive/5 text-destructive" : "border-border bg-secondary/30"
        }`}
      >
        <span className="font-medium">{isPending ? "Paused for approval" : isError ? "Tool error" : "Result"}</span>
        <pre className="mt-1 overflow-x-auto text-muted-foreground">
          {JSON.stringify(step.content, null, 2)}
        </pre>
      </div>
    );
  }

  // final_response
  return (
    <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
      <MarkdownContent content={String(step.content.content ?? "")} />
    </div>
  );
}
