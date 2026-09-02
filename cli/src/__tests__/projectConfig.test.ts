import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { findConfigFile, loadProjectConfig } from "../projectConfig.js";

// Real files on a real temp directory tree — projectConfig.ts's whole job is walking real
// directories and parsing a real YAML file, so faking fs would just be re-describing the code.
describe("loadProjectConfig", () => {
  let root: string;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), "kirxil-projectconfig-"));
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    rmSync(root, { recursive: true, force: true });
    consoleErrorSpy.mockRestore();
  });

  it("returns null when no .kirxil.yml exists anywhere up the tree", () => {
    const nested = join(root, "a", "b");
    mkdirSync(nested, { recursive: true });
    expect(loadProjectConfig(nested)).toBeNull();
  });

  it("reads project.name, model.default, and agent.max_iterations from the exact directory", () => {
    writeFileSync(
      join(root, ".kirxil.yml"),
      "project:\n  name: demo-project\nmodel:\n  default: qwen2.5:7b\nagent:\n  max_iterations: 6\n",
    );
    const config = loadProjectConfig(root);
    expect(config).toEqual({
      project: { name: "demo-project" },
      model: { default: "qwen2.5:7b" },
      agent: { max_iterations: 6 },
    });
  });

  it("reads a real verify: list", () => {
    writeFileSync(
      join(root, ".kirxil.yml"),
      "verify:\n  - npm run typecheck\n  - npm test\n  - npm run build\n",
    );
    const config = loadProjectConfig(root);
    expect(config?.verify).toEqual(["npm run typecheck", "npm test", "npm run build"]);
  });

  it("finds .kirxil.yml by walking up from a nested subdirectory", () => {
    writeFileSync(join(root, ".kirxil.yml"), "model:\n  default: llama3.1:8b\n");
    const nested = join(root, "src", "components");
    mkdirSync(nested, { recursive: true });
    const config = loadProjectConfig(nested);
    expect(config?.model?.default).toBe("llama3.1:8b");
  });

  it("returns null and warns, without throwing, on invalid YAML", () => {
    writeFileSync(join(root, ".kirxil.yml"), "model: [this is not: a valid: mapping\n");
    expect(loadProjectConfig(root)).toBeNull();
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  it("returns null and warns on YAML that doesn't match the expected shape", () => {
    writeFileSync(join(root, ".kirxil.yml"), "model: qwen2.5:7b\n");
    expect(loadProjectConfig(root)).toBeNull();
    expect(consoleErrorSpy).toHaveBeenCalled();
  });
});

describe("findConfigFile", () => {
  let root: string;

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), "kirxil-findconfig-"));
  });

  afterEach(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it("returns null when nothing is found (used by `kirxil config` to report that honestly)", () => {
    expect(findConfigFile(root)).toBeNull();
  });

  it("returns the real path to the config file it found, from a nested subdirectory", () => {
    writeFileSync(join(root, ".kirxil.yml"), "project:\n  name: demo\n");
    const nested = join(root, "a", "b");
    mkdirSync(nested, { recursive: true });
    expect(findConfigFile(nested)).toBe(join(root, ".kirxil.yml"));
  });
});
