import { apiFetch } from "@/lib/api/client";

export type RiskLevel = "low" | "medium" | "high" | "critical";
export type ExecutionStatus = "pending_approval" | "running" | "completed" | "failed" | "rejected";

export interface ToolOut {
  name: string;
  description: string;
  risk_level: RiskLevel;
  required_permission: string;
  input_schema: Record<string, unknown>;
}

export interface ToolExecutionOut {
  id: string;
  tool_name: string;
  risk_level: RiskLevel;
  status: ExecutionStatus;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export async function listTools(): Promise<ToolOut[]> {
  return apiFetch<ToolOut[]>("/tools");
}

export async function executeTool(
  toolName: string,
  input: Record<string, unknown>,
): Promise<ToolExecutionOut> {
  return apiFetch<ToolExecutionOut>(`/tools/${toolName}/execute`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/** Newest 50 for the tenant — the backend has no pagination for this endpoint. */
export async function listExecutions(): Promise<ToolExecutionOut[]> {
  return apiFetch<ToolExecutionOut[]>("/tools/executions");
}

/**
 * Really runs the tool. There's only one role today (owner, all permissions), so this always
 * succeeds in practice — the requester/approver separation the backend doesn't have yet.
 */
export async function approveExecution(id: string): Promise<ToolExecutionOut> {
  return apiFetch<ToolExecutionOut>(`/tools/executions/${id}/approve`, { method: "POST" });
}

export async function rejectExecution(id: string, reason?: string): Promise<ToolExecutionOut> {
  return apiFetch<ToolExecutionOut>(`/tools/executions/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}
