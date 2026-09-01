import { describe, expect, it } from "vitest";
import { buildVerbInstruction, VERBS } from "../verbs.js";

describe("VERBS", () => {
  it("covers the read/write split the PRD's command surface implies", () => {
    const names = VERBS.map((v) => v.name);
    expect(names).toEqual([
      "ask",
      "explain",
      "analyze",
      "generate",
      "refactor",
      "debug",
      "test",
      "review",
      "plan",
      "build",
    ]);
  });
});

describe("buildVerbInstruction", () => {
  it("ask includes the question and a read-only note", () => {
    const text = buildVerbInstruction("ask", "how does auth work?");
    expect(text).toContain("how does auth work?");
    expect(text).toContain("read-only");
  });

  it("explain names the target and stays read-only", () => {
    const text = buildVerbInstruction("explain", "app/agents/runner.py");
    expect(text).toContain('"app/agents/runner.py"');
    expect(text).toContain("read-only");
  });

  it("analyze falls back to 'the project' when no target is given", () => {
    const text = buildVerbInstruction("analyze", "");
    expect(text).toContain("the project in this directory");
  });

  it("generate is not marked read-only", () => {
    const text = buildVerbInstruction("generate", "a CLI flag parser");
    expect(text).toContain("a CLI flag parser");
    expect(text).not.toContain("read-only");
  });

  it("refactor mentions running existing tests afterward", () => {
    const text = buildVerbInstruction("refactor", "the login handler");
    expect(text).toContain("without changing its behavior");
    expect(text).toContain("run them afterward");
  });

  it("review asks for HIGH/MEDIUM/LOW severity tags and stays read-only", () => {
    const text = buildVerbInstruction("review", "");
    expect(text).toContain("HIGH, MEDIUM, or LOW");
    expect(text).toContain("read-only");
  });

  it("review includes an optional focus target when given", () => {
    const text = buildVerbInstruction("review", "the payment module");
    expect(text).toContain("focused on the payment module");
  });

  it("plan asks for a numbered PLAN, an estimate, and stays read-only", () => {
    const text = buildVerbInstruction("plan", "add subscription billing");
    expect(text).toContain("add subscription billing");
    expect(text).toContain("PLAN");
    expect(text).toContain("numbered steps");
    expect(text).toContain("Do not start implementing");
    expect(text).toContain("read-only");
  });

  it("build walks through Plan/Implement/Test/Review and is not read-only", () => {
    const text = buildVerbInstruction("build", "add a rate limiter");
    expect(text).toContain("add a rate limiter");
    expect(text).toContain("(1) Plan");
    expect(text).toContain("(2) Implement");
    expect(text).toContain("(3) Test");
    expect(text).toContain("(4) Review");
    expect(text).not.toContain("read-only");
  });
});
