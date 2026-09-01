import { describe, expect, it } from "vitest";
import { buildGoal, dirFromCwd } from "../goal.js";

describe("buildGoal", () => {
  it("frames a root-level goal without a folder qualifier", () => {
    const text = buildGoal("fix the bug", ".");
    expect(text).toContain("Using your host.list_files");
    expect(text).toContain("work in the real folder on this machine");
    expect(text.endsWith("Task: fix the bug")).toBe(true);
  });

  it("frames a subfolder goal with the folder prefix and a directory-argument instruction", () => {
    const text = buildGoal("fix the bug", "demo/app");
    expect(text).toContain('"demo/app" folder');
    expect(text).toContain("demo/app/");
    expect(text).toContain('pass "demo/app" as that argument');
    expect(text).toContain("do not also `cd` into it");
    expect(text.endsWith("Task: fix the bug")).toBe(true);
  });
});

describe("dirFromCwd", () => {
  it("returns '.' when launched at hostRoot itself", () => {
    expect(dirFromCwd("D:\\hostroot", "D:\\hostroot")).toBe(".");
  });

  it("returns a forward-slash relative path for a subfolder", () => {
    expect(dirFromCwd("D:\\hostroot", "D:\\hostroot\\demo\\app")).toBe("demo/app");
  });

  it("falls back to '.' when launched outside hostRoot entirely", () => {
    expect(dirFromCwd("D:\\hostroot", "E:\\elsewhere")).toBe(".");
  });
});
