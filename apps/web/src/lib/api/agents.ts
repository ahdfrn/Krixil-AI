import { apiFetch } from "@/lib/api/client";

export type AgentRunStatus = "running" | "completed" | "stopped" | "waiting_approval" | "failed";
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
 * Runs the entire planner/executor loop synchronously inside the request — can take up to
 * agent_max_execution_seconds (server-configured, default 120s) before this resolves. There's
 * nothing to poll: by the time this returns, the run has already reached a terminal or paused
 * status.
 */
export async function runAgent(goal: string): Promise<AgentRunOut> {
  return apiFetch<AgentRunOut>("/agents/run", {
    method: "POST",
    body: JSON.stringify({ goal }),
  });
}

/** Newest 50 for the tenant — the backend has no pagination for this endpoint. */
export async function listAgentRuns(): Promise<AgentRunOut[]> {
  return apiFetch<AgentRunOut[]>("/agents");
}

export async function getAgentRunStatus(id: string): Promise<AgentRunDetailOut> {
  return apiFetch<AgentRunDetailOut>(`/agents/${id}/status`);
}
