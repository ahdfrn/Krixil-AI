import { describe, expect, it } from "vitest";
import {
  buildToolCallArgsLookup,
  countTestAttempts,
  describeApprovalPrompt,
  describeInFlightStep,
  describeObservation,
  findInFlightToolCall,
  planPanelLines,
  summarizeToolCall,
  swarmChildStatusIcon,
} from "../render.js";
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
    expect(result.summary).toBe("Error");
  });

  it("labels a real BLOCK-tier outcome distinctly from an ordinary error", () => {
    const result = describeObservation(
      step({
        tool_name: "host.run_command",
        content: { error: "Blocked: recursive force-delete of the filesystem root — this command was not executed." },
      }),
    );
    expect(result.summary).toBe("🚫 Blocked");
    expect(result.tone).toBe("error");
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

  it("reports an edit as plain 'Edited' when no tool-call args are supplied", () => {
    const result = describeObservation(step({ tool_name: "host.edit_file", content: { path: "a.py", edited: true } }));
    expect(result).toEqual({ summary: "Edited", body: [], tone: "success" });
  });

  it("reports an edit as a real -/+ diff when tool-call args are supplied", () => {
    const result = describeObservation(
      step({ tool_name: "host.edit_file", content: { path: "a.py", edited: true } }),
      { old_string: "old line", new_string: "new line 1\nnew line 2" },
    );
    expect(result).toEqual({
      summary: "Edited (+2/-1)",
      body: ["- old line", "+ new line 1", "+ new line 2"],
      tone: "success",
    });
  });

  it("falls back to plain 'Edited' when tool-call args are missing old_string/new_string", () => {
    const result = describeObservation(
      step({ tool_name: "host.edit_file", content: { path: "a.py", edited: true } }),
      { path: "a.py" },
    );
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
    expect(result.riskLevel).toBe("high");
    expect(result.requireTypedConfirmation).toBe(false);
  });

  it("requires a typed confirmation for CRITICAL risk", () => {
    const result = describeApprovalPrompt("host.delete_file", "critical", { path: "important.py" });
    expect(result.riskLevel).toBe("critical");
    expect(result.requireTypedConfirmation).toBe(true);
  });
});

describe("buildToolCallArgsLookup", () => {
  it("maps each tool_call step's arguments by its own step_number", () => {
    const steps: AgentStep[] = [
      step({
        step_number: 1,
        type: "tool_call",
        tool_name: "host.edit_file",
        content: { arguments: { path: "a.py", old_string: "x", new_string: "y" } },
      }),
      step({ step_number: 1, type: "observation", tool_name: "host.edit_file", content: { path: "a.py", edited: true } }),
      step({ step_number: 2, type: "tool_call", tool_name: "host.write_file", content: { arguments: { path: "b.py" } } }),
    ];
    const lookup = buildToolCallArgsLookup(steps);
    expect(lookup.get(1)).toEqual({ path: "a.py", old_string: "x", new_string: "y" });
    expect(lookup.get(2)).toEqual({ path: "b.py" });
    expect(lookup.has(3)).toBe(false);
  });

  it("defaults to an empty object when a tool_call step has no arguments", () => {
    const steps: AgentStep[] = [step({ step_number: 1, type: "tool_call", tool_name: "host.list_files", content: {} })];
    expect(buildToolCallArgsLookup(steps).get(1)).toEqual({});
  });
});

describe("describeInFlightStep", () => {
  it("returns null for a missing tool name", () => {
    expect(describeInFlightStep(null, {})).toBeNull();
  });

  it("labels a test-looking run_command as 'Running tests…'", () => {
    expect(describeInFlightStep("host.run_command", { command: "pytest -q" })).toBe("Running tests…");
    expect(describeInFlightStep("host.run_command", { command: "npm test" })).toBe("Running tests…");
  });

  it("labels a non-test run_command as 'Running a command…'", () => {
    expect(describeInFlightStep("host.run_command", { command: "ls -la" })).toBe("Running a command…");
  });

  it("labels search/edit/write/read/list/delete tools", () => {
    expect(describeInFlightStep("host.search_files", {})).toBe("Searching…");
    expect(describeInFlightStep("host.edit_file", {})).toBe("Editing…");
    expect(describeInFlightStep("host.write_file", {})).toBe("Writing…");
    expect(describeInFlightStep("host.read_file", {})).toBe("Reading…");
    expect(describeInFlightStep("host.list_files", {})).toBe("Listing files…");
    expect(describeInFlightStep("host.delete_file", {})).toBe("Deleting…");
  });

  it("falls back to 'Working…' for an unrecognized tool", () => {
    expect(describeInFlightStep("some.other_tool", {})).toBe("Working…");
  });
});

describe("findInFlightToolCall", () => {
  it("returns null when every tool_call has a matching observation", () => {
    const steps: AgentStep[] = [
      step({ step_number: 1, type: "tool_call", tool_name: "host.read_file", content: { arguments: { path: "a.py" } } }),
      step({ step_number: 1, type: "observation", tool_name: "host.read_file", content: { content: "hi" } }),
    ];
    expect(findInFlightToolCall(steps)).toBeNull();
  });

  it("returns the most recent tool_call step that has no observation yet", () => {
    const steps: AgentStep[] = [
      step({ step_number: 1, type: "tool_call", tool_name: "host.read_file", content: { arguments: { path: "a.py" } } }),
      step({ step_number: 1, type: "observation", tool_name: "host.read_file", content: { content: "hi" } }),
      step({ step_number: 2, type: "tool_call", tool_name: "host.run_command", content: { arguments: { command: "pytest" } } }),
    ];
    const result = findInFlightToolCall(steps);
    expect(result?.step_number).toBe(2);
    expect(result?.tool_name).toBe("host.run_command");
  });
});

describe("countTestAttempts", () => {
  it("counts only run_command calls that look like a test invocation", () => {
    const steps: AgentStep[] = [
      step({ step_number: 1, type: "tool_call", tool_name: "host.run_command", content: { arguments: { command: "pytest -q" } } }),
      step({ step_number: 1, type: "observation", tool_name: "host.run_command", content: { exit_code: 1 } }),
      step({ step_number: 2, type: "tool_call", tool_name: "host.run_command", content: { arguments: { command: "ls" } } }),
      step({ step_number: 3, type: "tool_call", tool_name: "host.run_command", content: { arguments: { command: "npm test" } } }),
    ];
    expect(countTestAttempts(steps)).toBe(2);
  });

  it("returns 0 when there are no run_command calls at all", () => {
    const steps: AgentStep[] = [
      step({ step_number: 1, type: "tool_call", tool_name: "host.read_file", content: { arguments: { path: "a.py" } } }),
    ];
    expect(countTestAttempts(steps)).toBe(0);
  });
});

describe("planPanelLines", () => {
  it("wraps the real plan text with a top and bottom border and blank padding lines", () => {
    const lines = planPanelLines("PLAN\n1. Do the thing", 20);
    expect(lines[0]).toBe("┌─ KIRXIL PLAN ──────┐");
    expect(lines[lines.length - 1]).toBe("└────────────────────┘");
    expect(lines).toContain("PLAN");
    expect(lines).toContain("1. Do the thing");
  });

  it("preserves every real line of multi-line plan text, in order", () => {
    const lines = planPanelLines("a\nb\nc");
    const bodyStart = lines.indexOf("a");
    expect(lines.slice(bodyStart, bodyStart + 3)).toEqual(["a", "b", "c"]);
  });
});

describe("swarmChildStatusIcon", () => {
  it("maps every real status string to its own icon", () => {
    expect(swarmChildStatusIcon("running")).toBe("◉");
    expect(swarmChildStatusIcon("completed")).toBe("✓");
    expect(swarmChildStatusIcon("failed")).toBe("✗");
    expect(swarmChildStatusIcon("waiting_approval")).toBe("⏸");
    expect(swarmChildStatusIcon("cancelled")).toBe("○");
    expect(swarmChildStatusIcon("stopped")).toBe("○");
  });

  it("falls back to a neutral icon for an unrecognized status", () => {
    expect(swarmChildStatusIcon("something-new")).toBe("○");
  });
});
