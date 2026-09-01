import { apiFetch } from "@/lib/api/client";

export type AgentRunStatus =
  | "running"
  | "completed"
  | "stopped"
  | "waiting_approval"
  | "failed"
  | "cancelled";
export type AgentStepType = "tool_call" | "observation" | "final_response";

export interface AgentStepOut {
  step_number: number;
  type: AgentStepType;
  tool_name: string | null;
  content: Record<string, unknown>;
  created_at: string;
}

export interface AgentRunOut {
  id: string;
  goal: string;
  status: AgentRunStatus;
  step_count: number;
  tool_call_count: number;
  max_steps: number;
  max_tool_calls: number;
  final_response: string | null;
  error_message: string | null;
  pending_execution_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AgentRunDetailOut extends AgentRunOut {
  steps: AgentStepOut[];
}

/**
 * Returns the moment the run is created (status "running", no steps yet) — the planner/executor
 * loop itself now runs server-side as a background task, committing each step as it happens, so
 * the caller polls getAgentRunStatus/pollAgentRun to watch it happen live instead of blocking for
 * up to agent_max_execution_seconds.
 */
export async function runAgent(goal: string, model?: string): Promise<AgentRunOut> {
  return apiFetch<AgentRunOut>("/agents/run", {
    method: "POST",
    body: JSON.stringify({ goal, model }),
  });
}

/** Newest 50 for the tenant — the backend has no pagination for this endpoint. */
export async function listAgentRuns(): Promise<AgentRunOut[]> {
  return apiFetch<AgentRunOut[]>("/agents");
}

export async function getAgentRunStatus(id: string): Promise<AgentRunDetailOut> {
  return apiFetch<AgentRunDetailOut>(`/agents/${id}/status`);
}

/**
 * Claude Code's own "esc to interrupt" for a run still in progress. Doesn't kill anything
 * client-side — the loop notices on its next iteration and stops there (see app/agents/runner.py),
 * so the caller should keep polling afterward rather than assuming the run is dead the instant
 * this resolves. A no-op if the run already reached a terminal state.
 */
export async function cancelAgentRun(id: string): Promise<AgentRunOut> {
  return apiFetch<AgentRunOut>(`/agents/${id}/cancel`, { method: "POST" });
}

export interface PollHandle {
  cancel: () => void;
}

/**
 * Fetches the run's status every `intervalMs`, calling onUpdate with each result, until it
 * reaches a non-"running" status (completed/stopped/waiting_approval/failed) — this is what makes
 * a run's transcript render live, step by step, the way Claude Code's own tool-call feed does,
 * instead of appearing all at once when the whole thing finishes. Call .cancel() on unmount/close
 * to stop polling early (e.g. the user navigated away or closed the run's dialog); a network
 * error also stops the loop rather than retrying forever, leaving onUpdate's last known state as
 * the final one shown.
 */
export function pollAgentRun(
  id: string,
  onUpdate: (detail: AgentRunDetailOut) => void,
  intervalMs = 1200,
): PollHandle {
  let cancelled = false;

  void (async () => {
    for (;;) {
      let detail: AgentRunDetailOut;
      try {
        detail = await getAgentRunStatus(id);
      } catch {
        return;
      }
      if (cancelled) return;
      onUpdate(detail);
      if (detail.status !== "running") return;
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      if (cancelled) return;
    }
  })();

  return {
    cancel: () => {
      cancelled = true;
    },
  };
}
