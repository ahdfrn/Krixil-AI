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
  // Set only when this run is one real child of a Multi-Agent Swarm (POST /agents/swarm) — null
  // for every ordinary run.
  swarm_run_id: z.string().nullable(),
  // "native" | "hermes" — which AgentRuntime actually ran this (see app/agents/hermes_runtime.py).
  runtime: z.string(),
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

const SwarmRunSchema = z.object({
  id: z.string(),
  goal: z.string(),
  status: z.string(),
  model_id: z.string().nullable(),
  subtask_count: z.number(),
  synthesis: z.string().nullable(),
  error_message: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
});
export type SwarmRunOut = z.infer<typeof SwarmRunSchema>;

const SwarmChildSchema = AgentRunSchema.extend({
  // Real sibling AgentRun ids this child waits on (empty for an independent sub-task).
  depends_on: z.array(z.string()),
  // Only set for a dependent child whose `goal` got rewritten with injected prerequisite
  // context — the original, concise sub-task text, for display.
  original_goal: z.string().nullable(),
});
export type SwarmChildOut = z.infer<typeof SwarmChildSchema>;

const SwarmRunDetailSchema = SwarmRunSchema.extend({ children: z.array(SwarmChildSchema) });
export type SwarmRunDetail = z.infer<typeof SwarmRunDetailSchema>;

const BrainIndexRunSchema = z.object({
  id: z.string(),
  directory: z.string(),
  status: z.string(),
  file_count: z.number(),
  symbol_count: z.number(),
  chunk_count: z.number(),
  error_message: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
});
export type BrainIndexRunOut = z.infer<typeof BrainIndexRunSchema>;

const BrainSearchResultSchema = z.object({
  path: z.string(),
  language: z.string().nullable(),
  content: z.string(),
});
export type BrainSearchResultOut = z.infer<typeof BrainSearchResultSchema>;

const MCPServerSchema = z.object({
  id: z.string(),
  name: z.string(),
  transport: z.enum(["stdio", "sse", "http"]),
  command: z.string().nullable(),
  args: z.array(z.string()),
  // Real env/header values are redacted to "***" by the backend (app/mcp/router.py) — never sent
  // back over the API once set.
  env: z.record(z.string(), z.string()),
  url: z.string().nullable(),
  headers: z.record(z.string(), z.string()),
  created_at: z.string(),
});
export type MCPServerOut = z.infer<typeof MCPServerSchema>;

const MCPToolSchema = z.object({
  name: z.string(),
  description: z.string(),
  input_schema: z.record(z.string(), z.unknown()),
});
export type MCPToolOut = z.infer<typeof MCPToolSchema>;

const ToolExecutionSchema = z.object({
  id: z.string(),
  tool_name: z.string(),
  risk_level: z.enum(["low", "medium", "high", "critical"]),
  status: z.enum(["pending_approval", "running", "completed", "failed", "rejected", "blocked"]),
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
    private workspaceRoot?: string,
  ) {
    this.accessToken = accessToken;
  }

  private headers(): Record<string, string> {
    if (this.accessToken === null) throw new Error("Not logged in.");
    return { Authorization: `Bearer ${this.accessToken}`, "Content-Type": "application/json",
      ...(this.workspaceRoot ? { "X-Krixil-Workspace": encodeURIComponent(this.workspaceRoot) } : {}) };
  }

  async selectWorkspace(root: string): Promise<string> {
    const response = await fetch(`${this.baseUrl}/host/workspace`, {
      headers: { ...this.headers(), "X-Krixil-Workspace": encodeURIComponent(root) },
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) await parseError(response);
    const workspace = z.object({ root: z.string().min(1) }).parse(await response.json());
    this.workspaceRoot = workspace.root;
    return workspace.root;
  }

  async login(tenantSlug: string, email: string, password: string, totpCode?: string): Promise<{ accessToken: string; tenantSlug: string }> {
    const response = await fetch(`${this.baseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_slug: tenantSlug, email, password, ...(totpCode ? { totp_code: totpCode } : {}) }),
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

  async chat(message: string, conversationId?: string, model?: string, signal?: AbortSignal) {
    const response = await fetch(`${this.baseUrl}/chat`, {
      method: "POST",
      headers: this.headers(),
      signal,
      body: JSON.stringify({ message, conversation_id: conversationId ?? null, model: model ?? null, allow_tools: false }),
    });
    if (!response.ok) await parseError(response);
    return z.object({
      conversation_id: z.string(),
      message: z.object({ content: z.string() }),
      model: z.string(),
      provider: z.string().nullable().optional(),
    }).parse(await response.json());
  }

  async publicChat(message: string, signal?: AbortSignal) {
    const response = await fetch(`${this.baseUrl}/chat/public`, {
      method: "POST", headers: this.headers(), signal,
      body: JSON.stringify({ message, public_data_consent: true }),
    });
    if (!response.ok) await parseError(response);
    return z.object({ content: z.string(), model: z.string(), provider: z.string() }).parse(await response.json());
  }

  async runAgent(
    goal: string,
    model?: string,
    maxSteps?: number,
    runtime?: "native" | "hermes",
  ): Promise<AgentRunOut> {
    const response = await fetch(`${this.baseUrl}/agents/run`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({
        goal,
        model: model ?? null,
        max_steps: maxSteps ?? null,
        runtime: runtime ?? "native",
      }),
    });
    if (!response.ok) await parseError(response);
    return AgentRunSchema.parse(await response.json());
  }

  async runSwarm(goal: string, model?: string, maxSubtasks?: number): Promise<SwarmRunOut> {
    const response = await fetch(`${this.baseUrl}/agents/swarm`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({
        goal,
        model: model ?? null,
        max_subtasks: maxSubtasks ?? undefined,
      }),
    });
    if (!response.ok) await parseError(response);
    return SwarmRunSchema.parse(await response.json());
  }

  async getSwarmStatus(swarmRunId: string): Promise<SwarmRunDetail> {
    const response = await fetch(`${this.baseUrl}/agents/swarm/${swarmRunId}/status`, {
      headers: this.headers(),
    });
    if (!response.ok) await parseError(response);
    return SwarmRunDetailSchema.parse(await response.json());
  }

  async getStatus(runId: string): Promise<AgentRun> {
    const response = await fetch(`${this.baseUrl}/agents/${runId}/status`, { headers: this.headers() });
    if (!response.ok) await parseError(response);
    return AgentRunDetailSchema.parse(await response.json());
  }

  async indexBrain(directory = "."): Promise<BrainIndexRunOut> {
    const response = await fetch(`${this.baseUrl}/brain/index`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ directory }),
    });
    if (!response.ok) await parseError(response);
    return BrainIndexRunSchema.parse(await response.json());
  }

  async getBrainStatus(): Promise<BrainIndexRunOut | null> {
    const response = await fetch(`${this.baseUrl}/brain/status`, { headers: this.headers() });
    if (!response.ok) await parseError(response);
    const body = await response.json();
    return body === null ? null : BrainIndexRunSchema.parse(body);
  }

  async searchBrain(query: string, limit?: number): Promise<BrainSearchResultOut[]> {
    const response = await fetch(`${this.baseUrl}/brain/search`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ query, limit: limit ?? undefined }),
    });
    if (!response.ok) await parseError(response);
    return z.array(BrainSearchResultSchema).parse(await response.json());
  }

  async addMcpServer(
    name: string,
    opts:
      | { transport: "stdio"; command: string; args: string[]; env: Record<string, string> }
      | { transport: "sse" | "http"; url: string; headers: Record<string, string> },
  ): Promise<MCPServerOut> {
    const response = await fetch(`${this.baseUrl}/mcp/servers`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ name, ...opts }),
    });
    if (!response.ok) await parseError(response);
    return MCPServerSchema.parse(await response.json());
  }

  async listMcpServers(): Promise<MCPServerOut[]> {
    const response = await fetch(`${this.baseUrl}/mcp/servers`, { headers: this.headers() });
    if (!response.ok) await parseError(response);
    return z.array(MCPServerSchema).parse(await response.json());
  }

  async removeMcpServer(serverId: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/mcp/servers/${serverId}`, {
      method: "DELETE",
      headers: this.headers(),
    });
    if (!response.ok) await parseError(response);
  }

  async getMcpServerTools(serverId: string): Promise<MCPToolOut[]> {
    const response = await fetch(`${this.baseUrl}/mcp/servers/${serverId}/tools`, {
      headers: this.headers(),
    });
    if (!response.ok) await parseError(response);
    return z.array(MCPToolSchema).parse(await response.json());
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
