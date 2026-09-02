import { beforeEach, describe, expect, it, vi } from "vitest";
import { resolve } from "node:path";
const mocks = vi.hoisted(() => ({ load: vi.fn(), save: vi.fn(), prompt: vi.fn(), login: vi.fn(), models: vi.fn() }));
vi.mock("../config.js", () => ({ loadSession: mocks.load, saveSession: mocks.save }));
vi.mock("../prompt.js", () => ({ prompt: mocks.prompt }));
vi.mock("../api.js", async (original) => {
  const real = await original<typeof import("../api.js")>();
  return { ...real, KrixilApi: class { login = mocks.login; listModels = mocks.models; } };
});
import { ApiError } from "../api.js";
import { interactiveClient, selectedDirectory } from "../startup.js";
const saved = { baseUrl: "http://localhost/api/v1", tenantSlug: "test", accessToken: "test-token", hostRoot: resolve(process.cwd(), "..") };
beforeEach(() => {
  vi.resetAllMocks();
  vi.unstubAllEnvs();
  mocks.load.mockReturnValue(saved);
  mocks.models.mockResolvedValue([]);
  mocks.login.mockResolvedValue({ accessToken: "new-token", tenantSlug: "test" });
});
describe("interactive startup", () => {
  it("reuses a valid session without prompts", async () => {
    await interactiveClient();
    expect(mocks.prompt).not.toHaveBeenCalled();
    expect(mocks.login).not.toHaveBeenCalled();
  });
  it("expired session asks only email/password then saves token, not password", async () => {
    mocks.models.mockRejectedValue(new ApiError(401, "expired"));
    mocks.prompt.mockResolvedValueOnce("user@example.com").mockResolvedValueOnce(" secret ");
    await interactiveClient();
    expect(mocks.prompt.mock.calls).toEqual([["Email: "], ["Password: ", true]]);
    expect(mocks.login).toHaveBeenCalledWith("test", "user@example.com", " secret ");
    expect(mocks.save).toHaveBeenCalledWith({ ...saved, accessToken: "new-token", hostRoot: process.cwd() });
  });
  it.each([new TypeError("offline"), new ApiError(403, "forbidden"), new ApiError(503, "unavailable")])("does not relogin on %s", async (error) => {
    mocks.models.mockRejectedValue(error);
    await expect(interactiveClient()).rejects.toBe(error);
    expect(mocks.prompt).not.toHaveBeenCalled();
    expect(mocks.save).not.toHaveBeenCalled();
  });
  it("fresh setup prompts for tenant but never asks for a host root", async () => {
    mocks.load.mockReturnValue(null);
    vi.stubEnv("KRIXIL_TENANT_SLUG", undefined);
    vi.stubEnv("KRIXIL_HOST_ROOT", undefined);
    mocks.prompt.mockResolvedValueOnce("test").mockResolvedValueOnce("user@example.com").mockResolvedValueOnce("secret");
    await interactiveClient();
    expect(mocks.prompt).toHaveBeenCalledTimes(3);
    expect(mocks.save).toHaveBeenCalledOnce();
  });
  it("asks for 2FA without bypassing it", async () => {
    mocks.prompt.mockResolvedValueOnce("user@example.com").mockResolvedValueOnce("secret").mockResolvedValueOnce("123456");
    mocks.login.mockRejectedValueOnce(new ApiError(401, "2FA code required"));
    await interactiveClient(true);
    expect(mocks.login).toHaveBeenLastCalledWith("test", "user@example.com", "secret", "123456");
  });
  it("stops after three rejected logins without saving", async () => {
    mocks.prompt.mockResolvedValue("wrong");
    mocks.login.mockRejectedValue(new ApiError(401, "invalid"));
    await expect(interactiveClient(true)).rejects.toThrow("Login belum berhasil");
    expect(mocks.login).toHaveBeenCalledTimes(3);
    expect(mocks.save).not.toHaveBeenCalled();
  });
  it("preserves current directory and rejects paths outside root", () => {
    expect(selectedDirectory(saved.hostRoot, saved.hostRoot)).toBe(".");
    expect(selectedDirectory(saved.hostRoot, resolve(saved.hostRoot, "project", "src"))).toBe("project/src");
    expect(() => selectedDirectory(saved.hostRoot, resolve(saved.hostRoot, "..", "other"))).toThrow("di luar HOST_ROOT");
    expect(() => selectedDirectory("relative")).toThrow("absolut");
  });
});
