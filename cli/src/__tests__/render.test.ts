import { describe, expect, it } from "vitest";
import { describeApprovalPrompt, describeObservation, summarizeToolCall } from "../render.js";
import type { AgentStep } from "../api.js";

function step(overrides: Partial<AgentStep>): AgentStep {
  return { step_number: 1, type: "observation", tool_name: null, content: {}, created_at: "2026-09-01T00:00:00Z", ...overrides };
}

describe("summarizeToolCall", () => {
  it("summarizes a run_command call as Bash(...)", () => {
    expect(summarizeToolCall("host.run_command", { command: "pytest -q" })).toBe("Bash(pytest -q)");
  });

  it("includes the directory as a cd when one is given", () => {
    expect(summarizeToolCall("host.run_command", { command: "pytest -q", directory: "demo" })).toBe(
      "Bash(cd demo && pytest -q)",
    );
  });

  it("summarizes a write call as Write(path)", () => {
    expect(summarizeToolCall("host.write_file", { path: "a.py" })).toBe("Write(a.py)");
  });

  it("summarizes an edit call as Edit(path)", () => {
    expect(summarizeToolCall("host.edit_file", { path: "a.py", old_string: "x", new_string: "y" })).toBe(
      "Edit(a.py)",
    );
  });

  it("summarizes a search call as Search(pattern)", () => {
    expect(summarizeToolCall("host.search_files", { pattern: "def handler" })).toBe("Search(def handler)");
  });

  it("summarizes a delete call as Delete(path)", () => {
    expect(summarizeToolCall("host.delete_file", { path: "old.py" })).toBe("Delete(old.py)");
  });
});

describe("describeObservation", () => {
  it("reports a write as Saved", () => {
    const result = describeObservation(step({ tool_name: "host.write_file", content: { path: "a.py", written: true } }));
    expect(result).toEqual({ summary: "Saved", body: [], tone: "success" });
  });

  it("surfaces an error message and marks it error tone", () => {
    const result = describeObservation(step({ tool_name: "host.read_file", content: { error: "not found" } }));
    expect(result.tone).toBe("error");
    expect(result.body).toEqual(["not found"]);
  });

  it("reports a successful command's exit code and output", () => {
    const result = describeObservation(
      step({ tool_name: "host.run_command", content: { exit_code: 0, stdout: "ok\n", stderr: "", timed_out: false } }),
    );
    expect(result.summary).toBe("Exit 0");
    expect(result.tone).toBe("success");
    expect(result.body).toEqual(["ok"]);
  });

  it("marks a non-zero exit code as error tone", () => {
    const result = describeObservation(
      step({ tool_name: "host.run_command", content: { exit_code: 1, stdout: "", stderr: "boom", timed_out: false } }),
    );
    expect(result.tone).toBe("error");
    expect(result.body).toEqual(["boom"]);
  });

  it("lists file entries with a count", () => {
    const result = describeObservation(
      step({
        tool_name: "host.list_files",
        content: { entries: [{ name: "a.py", is_dir: false }, { name: "sub", is_dir: true }] },
      }),
    );
    expect(result.summary).toBe("Listed 2 paths");
    expect(result.body).toEqual(["a.py", "/sub"]);
  });

  it("reports an edit as Edited", () => {
    const result = describeObservation(step({ tool_name: "host.edit_file", content: { path: "a.py", edited: true } }));
    expect(result).toEqual({ summary: "Edited", body: [], tone: "success" });
  });

  it("reports search matches with path:line: text", () => {
    const result = describeObservation(
      step({
        tool_name: "host.search_files",
        content: { results: [{ path: "a.py", line_number: 3, line: "def handler():" }] },
      }),
    );
    expect(result.summary).toBe("1 match");
    expect(result.body).toEqual(["a.py:3: def handler():"]);
  });

  it("reports zero search matches as 'No matches'", () => {
    const result = describeObservation(step({ tool_name: "host.search_files", content: { results: [] } }));
    expect(result).toEqual({ summary: "No matches", body: [], tone: "muted" });
  });

  it("reports a delete as Deleted", () => {
    const result = describeObservation(step({ tool_name: "host.delete_file", content: { path: "old.py", deleted: true } }));
    expect(result).toEqual({ summary: "Deleted", body: [], tone: "success" });
  });

  it("marks a paused run as 'Paused for approval'", () => {
    const result = describeObservation(
      step({ tool_name: "host.run_command", content: { status: "pending_approval", execution_id: "exec-1" } }),
    );
    expect(result).toEqual({ summary: "Paused for approval", body: [], tone: "muted" });
  });
});

describe("describeApprovalPrompt", () => {
  it("reuses summarizeToolCall for the title and surfaces the risk level", () => {
    const result = describeApprovalPrompt("host.run_command", "high", { command: "pytest -q" });
    expect(result.title).toBe("Bash(pytest -q)");
    expect(result.detail).toBe("HIGH risk — approve to run it for real, or reject to stop this goal.");
  });
});
