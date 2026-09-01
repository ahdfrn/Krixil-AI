import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// config.ts resolves CONFIG_DIR/CREDENTIALS_PATH from os.homedir() at module load time, so the
// only reliable way to point it at a throwaway directory per test is mocking homedir() *before*
// importing the module — a fresh dynamic import per test gets a fresh evaluation of those consts.
async function freshConfig(home: string) {
  vi.resetModules();
  vi.doMock("node:os", async () => {
    const actual = await vi.importActual<typeof import("node:os")>("node:os");
    return { ...actual, homedir: () => home };
  });
  return import("../config.js");
}

describe("config", () => {
  let tmpHome: string;

  beforeEach(() => {
    tmpHome = mkdtempSync(join(tmpdir(), "krixil-cli-test-"));
  });

  afterEach(() => {
    rmSync(tmpHome, { recursive: true, force: true });
    vi.doUnmock("node:os");
  });

  it("returns null when nothing has been saved", async () => {
    const config = await freshConfig(tmpHome);
    expect(config.loadSession()).toBeNull();
  });

  it("saves then loads the same session", async () => {
    const config = await freshConfig(tmpHome);
    const session = { baseUrl: "http://localhost:8000/api/v1", tenantSlug: "acme-1", accessToken: "tok-123", hostRoot: "D:\\" };
    config.saveSession(session);
    expect(config.loadSession()).toEqual(session);
  });

  it("clearSession removes the file", async () => {
    const config = await freshConfig(tmpHome);
    config.saveSession({ baseUrl: "x", tenantSlug: "y", accessToken: "z", hostRoot: "D:\\" });
    config.clearSession();
    expect(existsSync(config.paths.CREDENTIALS_PATH)).toBe(false);
    expect(config.loadSession()).toBeNull();
  });

  it("envLogin requires all three variables", async () => {
    const config = await freshConfig(tmpHome);
    delete process.env.KRIXIL_TENANT_SLUG;
    delete process.env.KRIXIL_EMAIL;
    delete process.env.KRIXIL_PASSWORD;
    expect(config.envLogin()).toBeNull();

    process.env.KRIXIL_TENANT_SLUG = "acme-1";
    process.env.KRIXIL_EMAIL = "a@b.dev";
    process.env.KRIXIL_PASSWORD = "correct-horse-battery";
    expect(config.envLogin()).toEqual({ tenantSlug: "acme-1", email: "a@b.dev", password: "correct-horse-battery" });
    delete process.env.KRIXIL_TENANT_SLUG;
    delete process.env.KRIXIL_EMAIL;
    delete process.env.KRIXIL_PASSWORD;
  });
});
