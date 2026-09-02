import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, KrixilApi } from "../api.js";

const BASE_URL = "http://mock.krixil.test/api/v1";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("KrixilApi", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("login stores the token and returns the tenant slug", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        access_token: "tok-123",
        token_type: "bearer",
        expires_in: 3600,
        user: { id: "u1", email: "a@b.dev" },
        tenant: { id: "t1", name: "Acme", slug: "acme-1" },
      }),
    );
    const api = new KrixilApi(BASE_URL);
    const result = await api.login("acme-1", "a@b.dev", "correct-horse-battery");
    expect(result).toEqual({ accessToken: "tok-123", tenantSlug: "acme-1" });
  });

  it("login failure raises an ApiError with the real detail", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Invalid credentials" }, 401));
    const api = new KrixilApi(BASE_URL);
    await expect(api.login("acme-1", "a@b.dev", "wrong")).rejects.toThrow(ApiError);
  });

  it("runAgent sends the goal and model, with the bearer token attached", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "run-1",
        goal: "do the thing",
        status: "running",
        step_count: 0,
        tool_call_count: 0,
        max_steps: 8,
        max_tool_calls: 5,
        final_response: null,
        error_message: null,
        pending_execution_id: null,
        swarm_run_id: null,
        created_at: "2026-09-01T00:00:00Z",
        completed_at: null,
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const run = await api.runAgent("do the thing", "llama3.1:8b");
    expect(run.id).toBe("run-1");
    expect(run.status).toBe("running");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-123");
    expect(JSON.parse(init.body as string)).toEqual({ goal: "do the thing", model: "llama3.1:8b", max_steps: null });
  });

  it("runAgent forwards maxSteps when given (PRD §34's agent.max_iterations)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "run-1",
        goal: "do the thing",
        status: "running",
        step_count: 0,
        tool_call_count: 0,
        max_steps: 4,
        max_tool_calls: 5,
        final_response: null,
        error_message: null,
        pending_execution_id: null,
        swarm_run_id: null,
        created_at: "2026-09-01T00:00:00Z",
        completed_at: null,
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    await api.runAgent("do the thing", "auto", 4);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ goal: "do the thing", model: "auto", max_steps: 4 });
  });

  it("getStatus returns the run's steps", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "run-1",
        goal: "do the thing",
        status: "completed",
        step_count: 1,
        tool_call_count: 0,
        max_steps: 8,
        max_tool_calls: 5,
        final_response: "Done.",
        error_message: null,
        pending_execution_id: null,
        swarm_run_id: null,
        created_at: "2026-09-01T00:00:00Z",
        completed_at: "2026-09-01T00:00:05Z",
        steps: [
          { step_number: 1, type: "final_response", tool_name: null, content: { content: "Done." }, created_at: "2026-09-01T00:00:05Z" },
        ],
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const run = await api.getStatus("run-1");
    expect(run.status).toBe("completed");
    expect(run.steps).toHaveLength(1);
  });

  it("throws when no token is set", async () => {
    const api = new KrixilApi(BASE_URL);
    await expect(api.listModels()).rejects.toThrow("Not logged in.");
  });

  it("getExecution parses a pending tool execution", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "exec-1",
        tool_name: "host.run_command",
        risk_level: "high",
        status: "pending_approval",
        input: { command: "pytest -q", directory: "." },
        output: null,
        error_message: null,
        created_at: "2026-09-01T00:00:00Z",
        completed_at: null,
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const execution = await api.getExecution("exec-1");
    expect(execution.risk_level).toBe("high");
    expect(execution.status).toBe("pending_approval");
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${BASE_URL}/tools/executions/exec-1`);
  });

  it("approveExecution posts to the approve endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "exec-1",
        tool_name: "host.run_command",
        risk_level: "high",
        status: "completed",
        input: { command: "pytest -q" },
        output: { stdout: "ok\n", stderr: "", exit_code: 0, timed_out: false },
        error_message: null,
        created_at: "2026-09-01T00:00:00Z",
        completed_at: "2026-09-01T00:00:02Z",
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const execution = await api.approveExecution("exec-1");
    expect(execution.status).toBe("completed");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/tools/executions/exec-1/approve`);
    expect(init.method).toBe("POST");
  });

  it("rejectExecution posts a reason to the reject endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "exec-1",
        tool_name: "host.run_command",
        risk_level: "high",
        status: "rejected",
        input: { command: "pytest -q" },
        output: null,
        error_message: "too risky",
        created_at: "2026-09-01T00:00:00Z",
        completed_at: "2026-09-01T00:00:02Z",
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const execution = await api.rejectExecution("exec-1", "too risky");
    expect(execution.status).toBe("rejected");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/tools/executions/exec-1/reject`);
    expect(JSON.parse(init.body as string)).toEqual({ reason: "too risky" });
  });

  it("listMemories parses the list", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([{ id: "mem-1", content: "User prefers dark mode.", created_at: "2026-09-01T00:00:00Z" }]),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const memories = await api.listMemories();
    expect(memories).toHaveLength(1);
    expect(memories[0]?.content).toBe("User prefers dark mode.");
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${BASE_URL}/memory`);
  });

  it("addMemory posts the content and returns the created memory", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ id: "mem-2", content: "Ships on Fridays.", created_at: "2026-09-01T00:00:00Z" }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const memory = await api.addMemory("Ships on Fridays.");
    expect(memory.id).toBe("mem-2");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/memory`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ content: "Ships on Fridays." });
  });

  it("forgetMemory deletes by id and doesn't try to parse an empty 204 body", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const api = new KrixilApi(BASE_URL, "tok-123");
    await api.forgetMemory("mem-1");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/memory/mem-1`);
    expect(init.method).toBe("DELETE");
  });

  it("getMemorySettings returns the enabled flag", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ memory_enabled: false }));
    const api = new KrixilApi(BASE_URL, "tok-123");
    expect(await api.getMemorySettings()).toBe(false);
  });

  it("setMemorySettings patches and returns the new value", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ memory_enabled: true }));
    const api = new KrixilApi(BASE_URL, "tok-123");
    const result = await api.setMemorySettings(true);
    expect(result).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/memory/settings`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ enabled: true });
  });

  it("runSwarm sends the goal, model, and max_subtasks", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "swarm-1",
        goal: "make this production ready",
        status: "running",
        model_id: null,
        subtask_count: 0,
        synthesis: null,
        error_message: null,
        created_at: "2026-09-02T00:00:00Z",
        completed_at: null,
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const swarm = await api.runSwarm("make this production ready", "auto", 4);
    expect(swarm.id).toBe("swarm-1");
    expect(swarm.status).toBe("running");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/agents/swarm`);
    expect(JSON.parse(init.body as string)).toEqual({
      goal: "make this production ready",
      model: "auto",
      max_subtasks: 4,
    });
  });

  it("getSwarmStatus returns the swarm and its real children", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "swarm-1",
        goal: "make this production ready",
        status: "completed",
        model_id: null,
        subtask_count: 2,
        synthesis: "Combined report.",
        error_message: null,
        created_at: "2026-09-02T00:00:00Z",
        completed_at: "2026-09-02T00:01:00Z",
        children: [
          {
            id: "child-1",
            goal: "Security audit",
            status: "completed",
            step_count: 1,
            tool_call_count: 0,
            max_steps: 8,
            max_tool_calls: 5,
            final_response: "No issues found.",
            error_message: null,
            pending_execution_id: null,
            swarm_run_id: "swarm-1",
            created_at: "2026-09-02T00:00:00Z",
            completed_at: "2026-09-02T00:00:30Z",
          },
        ],
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const swarm = await api.getSwarmStatus("swarm-1");
    expect(swarm.status).toBe("completed");
    expect(swarm.synthesis).toBe("Combined report.");
    expect(swarm.children).toHaveLength(1);
    expect(swarm.children[0]!.goal).toBe("Security audit");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/agents/swarm/swarm-1/status`);
  });

  it("indexBrain posts the real directory and parses the started run", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "index-1",
        directory: "my-project",
        status: "running",
        file_count: 0,
        symbol_count: 0,
        chunk_count: 0,
        error_message: null,
        created_at: "2026-09-02T00:00:00Z",
        completed_at: null,
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const run = await api.indexBrain("my-project");
    expect(run.status).toBe("running");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/brain/index`);
    expect(JSON.parse(init.body as string)).toEqual({ directory: "my-project" });
  });

  it("getBrainStatus returns null when nothing has been indexed yet", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(null));
    const api = new KrixilApi(BASE_URL, "tok-123");
    expect(await api.getBrainStatus()).toBeNull();
  });

  it("getBrainStatus parses a real completed run with real counts", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "index-1",
        directory: ".",
        status: "completed",
        file_count: 12,
        symbol_count: 47,
        chunk_count: 30,
        error_message: null,
        created_at: "2026-09-02T00:00:00Z",
        completed_at: "2026-09-02T00:00:20Z",
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const run = await api.getBrainStatus();
    expect(run?.file_count).toBe(12);
    expect(run?.symbol_count).toBe(47);
    expect(run?.chunk_count).toBe(30);
  });

  it("searchBrain sends the query and real limit, and parses real results", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        { path: "app.py", language: "python", content: "def handler(): ..." },
      ]),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const results = await api.searchBrain("handle a request", 5);
    expect(results).toHaveLength(1);
    expect(results[0]!.path).toBe("app.py");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/brain/search`);
    expect(JSON.parse(init.body as string)).toEqual({ query: "handle a request", limit: 5 });
  });

  it("addMcpServer posts the real name/command/args/env", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "srv-1",
        name: "fs",
        command: "npx",
        args: ["-y", "@modelcontextprotocol/server-filesystem", "D:\\demo"],
        env: {},
        created_at: "2026-09-02T00:00:00Z",
      }),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const server = await api.addMcpServer(
      "fs",
      "npx",
      ["-y", "@modelcontextprotocol/server-filesystem", "D:\\demo"],
      {},
    );
    expect(server.name).toBe("fs");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/mcp/servers`);
    expect(JSON.parse(init.body as string)).toEqual({
      name: "fs",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-filesystem", "D:\\demo"],
      env: {},
    });
  });

  it("listMcpServers returns real configured servers with redacted env", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          id: "srv-1",
          name: "fs",
          command: "npx",
          args: [],
          env: { API_TOKEN: "***" },
          created_at: "2026-09-02T00:00:00Z",
        },
      ]),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const servers = await api.listMcpServers();
    expect(servers).toHaveLength(1);
    expect(servers[0]!.env).toEqual({ API_TOKEN: "***" });
  });

  it("removeMcpServer sends a real DELETE by id", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const api = new KrixilApi(BASE_URL, "tok-123");
    await api.removeMcpServer("srv-1");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/mcp/servers/srv-1`);
    expect(init.method).toBe("DELETE");
  });

  it("getMcpServerTools returns the real tools a server advertises", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([{ name: "add", description: "Add two numbers.", input_schema: {} }]),
    );
    const api = new KrixilApi(BASE_URL, "tok-123");
    const tools = await api.getMcpServerTools("srv-1");
    expect(tools).toHaveLength(1);
    expect(tools[0]!.name).toBe("add");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/mcp/servers/srv-1/tools`);
  });
});
