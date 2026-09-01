/**
 * Thin HTTP client for the Krixil api service's Agent endpoints — same shape as
 * apps/web/src/lib/api/agents.ts and cli-python/krixil_cli/api.py. Native fetch, no SDK, no HTTP
 * library dependency.
 */

import { z } from "zod";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

const AgentStepSchema = z.object({
  step_number: z.number(),
  type: z.string(),
  tool_name: z.string().nullable(),
  content: z.record(z.string(), z.unknown()),
  created_at: z.string(),
});
export type AgentStep = z.infer<typeof AgentStepSchema>;

const AgentRunSchema = z.object({
  id: z.string(),
  goal: z.string(),
  status: z.string(),
  step_count: z.number(),
  tool_call_count: z.number(),
  max_steps: z.number(),
  max_tool_calls: z.number(),
  final_response: z.string().nullable(),
  error_message: z.string().nullable(),
  pending_execution_id: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
});
export type AgentRunOut = z.infer<typeof AgentRunSchema>;

const AgentRunDetailSchema = AgentRunSchema.extend({ steps: z.array(AgentStepSchema) });
export type AgentRun = z.infer<typeof AgentRunDetailSchema>;

const ModelSchema = z.object({ id: z.string(), name: z.string(), description: z.string() });
export type ModelInfo = z.infer<typeof ModelSchema>;

const MemorySchema = z.object({ id: z.string(), content: z.string(), created_at: z.string() });
export type MemoryOut = z.infer<typeof MemorySchema>;

const ToolExecutionSchema = z.object({
  id: z.string(),
  tool_name: z.string(),
  risk_level: z.enum(["low", "medium", "high", "critical"]),
  status: z.enum(["pending_approval", "running", "completed", "failed", "rejected"]),
  input: z.record(z.string(), z.unknown()),
  output: z.record(z.string(), z.unknown()).nullable(),
  error_message: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
});
export type ToolExecutionOut = z.infer<typeof ToolExecutionSchema>;

async function parseError(response: Response): Promise<never> {
  let detail = response.statusText;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) {
      detail = body.detail
        .map((d) => (typeof d === "object" && d !== null && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
        .join("; ");
    }
  } catch {
    // response body wasn't JSON — fall back to statusText
  }
  throw new ApiError(response.status, detail);
}

export class KrixilApi {
  private accessToken: string | null;

  constructor(
    private baseUrl: string,
    accessToken: string | null = null,
  ) {
    this.accessToken = accessToken;
  }

  private headers(): Record<string, string> {
    if (this.accessToken === null) throw new Error("Not logged in.");
    return { Authorization: `Bearer ${this.accessToken}`, "Content-Type": "application/json" };
  }

  async login(tenantSlug: string, email: string, password: string): Promise<{ accessToken: string; tenantSlug: string }> {
    const response = await fetch(`${this.baseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_slug: tenantSlug, email, password }),
    });
    if (!response.ok) await parseError(response);
    const body = (await response.json()) as { access_token: string; tenant: { slug: string } };
    this.accessToken = body.access_token;
    return { accessToken: body.access_token, tenantSlug: body.tenant.slug };
  }

  async listModels(): Promise<ModelInfo[]> {
    const response = await fetch(`${this.baseUrl}/models`, { headers: this.headers() });
    if (!response.ok) await parseError(response);
    return z.array(ModelSchema).parse(await response.json());
  }

  async listRuns(): Promise<AgentRunOut[]> {
    const response = await fetch(`${this.baseUrl}/agents`, { headers: this.headers() });
    if (!response.ok) await parseError(response);
    return z.array(AgentRunSchema).parse(await response.json());
  }

  async runAgent(goal: string, model?: string, maxSteps?: number): Promise<AgentRunOut> {
    const response = await fetch(`${this.baseUrl}/agents/run`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ goal, model: model ?? null, max_steps: maxSteps ?? null }),
    });
    if (!response.ok) await parseError(response);
    return AgentRunSchema.parse(await response.json());
  }

  async getStatus(runId: string): Promise<AgentRun> {
    const response = await fetch(`${this.baseUrl}/agents/${runId}/status`, { headers: this.headers() });
    if (!response.ok) await parseError(response);
    return AgentRunDetailSchema.parse(await response.json());
  }

  async cancel(runId: string): Promise<AgentRunOut> {
    const response = await fetch(`${this.baseUrl}/agents/${runId}/cancel`, {
      method: "POST",
      headers: this.headers(),
    });
    if (!response.ok) await parseError(response);
    return AgentRunSchema.parse(await response.json());
  }

  async getExecution(executionId: string): Promise<ToolExecutionOut> {
    const response = await fetch(`${this.baseUrl}/tools/executions/${executionId}`, {
      headers: this.headers(),
    });
    if (!response.ok) await parseError(response);
    return ToolExecutionSchema.parse(await response.json());
  }

  async approveExecution(executionId: string): Promise<ToolExecutionOut> {
    const response = await fetch(`${this.baseUrl}/tools/executions/${executionId}/approve`, {
      method: "POST",
      headers: this.headers(),
    });
    if (!response.ok) await parseError(response);
    return ToolExecutionSchema.parse(await response.json());
  }

  async rejectExecution(executionId: string, reason?: string): Promise<ToolExecutionOut> {
    const response = await fetch(`${this.baseUrl}/tools/executions/${executionId}/reject`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ reason: reason ?? null }),
    });
    if (!response.ok) await parseError(response);
    return ToolExecutionSchema.parse(await response.json());
  }

  async listMemories(): Promise<MemoryOut[]> {
    const response = await fetch(`${this.baseUrl}/memory`, { headers: this.headers() });
    if (!response.ok) await parseError(response);
    return z.array(MemorySchema).parse(await response.json());
  }

  async addMemory(content: string): Promise<MemoryOut> {
    const response = await fetch(`${this.baseUrl}/memory`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ content }),
    });
    if (!response.ok) await parseError(response);
    return MemorySchema.parse(await response.json());
  }

  async forgetMemory(memoryId: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/memory/${memoryId}`, {
      method: "DELETE",
      headers: this.headers(),
    });
    if (!response.ok) await parseError(response);
  }

  async getMemorySettings(): Promise<boolean> {
    const response = await fetch(`${this.baseUrl}/memory/settings`, { headers: this.headers() });
    if (!response.ok) await parseError(response);
    const body = (await response.json()) as { memory_enabled: boolean };
    return body.memory_enabled;
  }

  async setMemorySettings(enabled: boolean): Promise<boolean> {
    const response = await fetch(`${this.baseUrl}/memory/settings`, {
      method: "PATCH",
      headers: this.headers(),
      body: JSON.stringify({ enabled }),
    });
    if (!response.ok) await parseError(response);
    const body = (await response.json()) as { memory_enabled: boolean };
    return body.memory_enabled;
  }
}
