/**
 * Real Ink-render tests for the components ui/*.tsx can't otherwise be checked by — a pure
 * render.ts test proves the data-shaping logic is right, but not that Yoga's flexbox actually
 * lays it out sanely. Caught live: StatusBar's two sides ran together with zero gap between them
 * because a Box with no explicit width has nothing for justifyContent: "space-between" to
 * distribute — this file exists so that class of bug doesn't come back silently.
 */
import React from "react";
import { render } from "ink-testing-library";
import { describe, expect, it } from "vitest";
import { StatusBar } from "../ui/StatusBar.js";
import { RunSummary, Transcript } from "../ui/Transcript.js";
import { SwarmTree } from "../ui/SwarmTree.js";
import { App } from "../ui/App.js";
import type { AgentStep, AgentRunOut, KrixilApi, SwarmRunDetail } from "../api.js";

const UP = "[A";
const DOWN = "[B";
const ENTER = "\r";

function step(overrides: Partial<AgentStep>): AgentStep {
  return { step_number: 1, type: "observation", tool_name: null, content: {}, created_at: "2026-09-01T00:00:00Z", ...overrides };
}

function swarmChild(overrides: Partial<AgentRunOut>): AgentRunOut {
  return {
    id: "child-1",
    goal: "sub-task",
    status: "running",
    step_count: 0,
    tool_call_count: 0,
    max_steps: 20,
    max_tool_calls: 20,
    final_response: null,
    error_message: null,
    pending_execution_id: null,
    swarm_run_id: "swarm-1",
    created_at: "2026-09-01T00:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

function fakeApi(swarm: SwarmRunDetail): KrixilApi {
  return { getSwarmStatus: async () => swarm } as unknown as KrixilApi;
}

describe("StatusBar", () => {
  it("keeps a real gap between the summary and the keyboard hints", () => {
    const { lastFrame, unmount } = render(<StatusBar toolCalls={3} testOutcomes={["failed", "passed"]} />);
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toContain("3 tool calls");
    expect(frame).toContain("tests ✗ ✓ (passing)");
    expect(frame).toContain("/help /model /cwd /expand /undo /exit");
    // The regression this guards: summary and hints must not be directly adjacent with no
    // whitespace between them (e.g. "...(passing)/help..." instead of "...(passing)   /help...").
    expect(frame).not.toMatch(/\)\/help/);
  });

  it("omits the tests segment when there are no test attempts", () => {
    const { lastFrame, unmount } = render(<StatusBar toolCalls={0} testOutcomes={[]} />);
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toContain("0 tool calls");
    expect(frame).not.toContain("tests");
  });
});

describe("RunSummary", () => {
  const toolCallStep = step({ step_number: 1, type: "tool_call", tool_name: "host.read_file", content: {} });

  it("shows a real tool-call count and test outcome sequence for a completed run", () => {
    const steps: AgentStep[] = [
      toolCallStep,
      step({ step_number: 2, type: "tool_call", tool_name: "host.run_command", content: { arguments: { command: "npm test" } } }),
      step({ step_number: 2, type: "observation", tool_name: "host.run_command", content: { exit_code: 0 } }),
    ];
    const { lastFrame, unmount } = render(<RunSummary steps={steps} status="completed" />);
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toContain("2 tool calls");
    expect(frame).toContain("tests ✓ (passing)");
  });

  it("renders nothing for a run still in progress", () => {
    const { lastFrame, unmount } = render(<RunSummary steps={[toolCallStep]} status="running" />);
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toBe("");
  });

  it("renders nothing for a completed run with no tool calls", () => {
    const { lastFrame, unmount } = render(<RunSummary steps={[]} status="completed" />);
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toBe("");
  });
});

describe("SwarmTree", () => {
  it("draws a real branch per sub-task with its own status and tool-call count", async () => {
    const swarm: SwarmRunDetail = {
      id: "swarm-1",
      goal: "make this production ready",
      status: "completed",
      model_id: null,
      subtask_count: 2,
      synthesis: "Both sub-tasks are done; the app is ready.",
      error_message: null,
      created_at: "2026-09-01T00:00:00Z",
      completed_at: "2026-09-01T00:05:00Z",
      children: [
        swarmChild({ id: "a", goal: "Audit security", status: "completed", tool_call_count: 4 }),
        swarmChild({ id: "b", goal: "Review tests", status: "failed", tool_call_count: 1, error_message: "boom" }),
      ],
    };
    const { lastFrame, unmount } = render(
      <SwarmTree api={fakeApi(swarm)} goal={swarm.goal} swarmRunId={swarm.id} />,
    );
    await new Promise((resolve) => setTimeout(resolve, 10));
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toContain("ORCHESTRATOR — 2 sub-tasks");
    expect(frame).toContain("✓ Audit security");
    expect(frame).toContain("(4 tool calls — completed)");
    expect(frame).toContain("✗ Review tests");
    expect(frame).toContain("(1 tool call — failed)");
    expect(frame).toContain("SYNTHESIS");
    expect(frame).toContain("Both sub-tasks are done");
  });

  it("shows the real failure reason when the whole swarm fails, not just its children", async () => {
    const swarm: SwarmRunDetail = {
      id: "swarm-2",
      goal: "goal",
      status: "failed",
      model_id: null,
      subtask_count: 1,
      synthesis: null,
      error_message: "The decomposition call failed.",
      created_at: "2026-09-01T00:00:00Z",
      completed_at: "2026-09-01T00:01:00Z",
      children: [],
    };
    const { lastFrame, unmount } = render(
      <SwarmTree api={fakeApi(swarm)} goal={swarm.goal} swarmRunId={swarm.id} />,
    );
    await new Promise((resolve) => setTimeout(resolve, 10));
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toContain("The decomposition call failed.");
  });
});

describe("Transcript expand/collapse", () => {
  function longOutputSteps(): AgentStep[] {
    const stdout = Array.from({ length: 45 }, (_, i) => `line ${i}`).join("\n");
    return [
      step({ step_number: 1, type: "tool_call", tool_name: "host.run_command", content: { arguments: { command: "build" } } }),
      step({ step_number: 1, type: "observation", tool_name: "host.run_command", content: { exit_code: 0, stdout, stderr: "" } }),
    ];
  }

  it("clips output beyond MAX_OUTPUT_LINES by default", () => {
    const { lastFrame, unmount } = render(<Transcript goal="build it" steps={longOutputSteps()} status="completed" elapsedSeconds={0} />);
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toContain("line 39");
    expect(frame).not.toContain("line 40");
    expect(frame).toContain("… and 5 more lines");
  });

  it("shows every real line when expanded is true", () => {
    const { lastFrame, unmount } = render(
      <Transcript goal="build it" steps={longOutputSteps()} status="completed" elapsedSeconds={0} expanded />,
    );
    const frame = lastFrame() ?? "";
    unmount();
    expect(frame).toContain("line 44");
    expect(frame).not.toContain("more lines");
  });
});

describe("App input history (Up/Down)", () => {
  const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

  it("recalls previously submitted commands with Up, and Down walks back toward the live draft", async () => {
    const fakeApi = { listModels: async () => [] } as unknown as KrixilApi;
    const { stdin, lastFrame, unmount } = render(<App api={fakeApi} hostRoot="D:\\" initialDir="." />);
    await tick(); // let Ink finish mounting/attaching stdin before the first write

    stdin.write("/help");
    await tick();
    stdin.write(ENTER);
    await tick();

    stdin.write("/cwd");
    await tick();
    stdin.write(ENTER);
    await tick();

    // Both /help and /cwd resolve locally (no API call) and are real submitted entries, newest
    // last — Up should recall /cwd first, then /help.
    stdin.write(UP);
    await tick();
    expect(lastFrame() ?? "").toContain("> /cwd");

    stdin.write(UP);
    await tick();
    expect(lastFrame() ?? "").toContain("> /help");

    stdin.write(DOWN);
    await tick();
    expect(lastFrame() ?? "").toContain("> /cwd");

    stdin.write(DOWN);
    await tick();
    // Past the newest entry restores the draft — empty here, since nothing was being typed.
    const frame = lastFrame() ?? "";
    expect(frame).not.toContain("> /cwd");
    expect(frame).not.toContain("> /help");

    unmount();
  });

  it("clears the visible run history on Ctrl+L without crashing", async () => {
    const fakeApi = { listModels: async () => [] } as unknown as KrixilApi;
    const { stdin, lastFrame, unmount } = render(<App api={fakeApi} hostRoot="D:\\" initialDir="." />);
    await tick(); // let Ink finish mounting/attaching stdin before the first write
    stdin.write("\f"); // Ctrl+L
    await tick();
    expect(lastFrame() ?? "").toContain(">");
    unmount();
  });
});
