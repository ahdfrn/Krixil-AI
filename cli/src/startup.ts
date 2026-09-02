import { isAbsolute, relative, resolve, sep } from "node:path";
import { ApiError, KrixilApi } from "./api.js";
import { loadSession, saveSession } from "./config.js";
import { prompt } from "./prompt.js";

export function selectedDirectory(hostRoot: string, cwd = process.cwd()): string {
  if (!isAbsolute(hostRoot)) throw new Error("HOST_ROOT harus berupa path absolut.");
  const dir = relative(resolve(hostRoot), resolve(cwd));
  if (dir === ".." || dir.startsWith(`..${sep}`) || isAbsolute(dir)) {
    throw new Error(`Folder ${cwd} berada di luar HOST_ROOT ${hostRoot}. Pilih folder di dalam batas akses host-runner.`);
  }
  return dir.split(sep).join("/") || ".";
}

export async function interactiveClient(forceLogin = false, baseUrlOverride?: string) {
  const stored = loadSession();
  const baseUrl = baseUrlOverride ?? stored?.baseUrl ?? process.env.KRIXIL_BASE_URL ?? "http://localhost:8000/api/v1";
  const sameServer = !baseUrlOverride || baseUrlOverride === stored?.baseUrl;
  if (stored && sameServer && !forceLogin) {
    const api = new KrixilApi(baseUrl, stored.accessToken);
    try {
      await api.listModels();
      return { api, hostRoot: process.cwd() };
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      console.log("Sesi berakhir. Silakan login kembali.");
    }
  }
  console.log("KIRXIL AI · Login");
  const tenantSlug = (sameServer ? stored?.tenantSlug : undefined) ?? process.env.KRIXIL_TENANT_SLUG ?? await prompt("Workspace slug (setup pertama): ");
  const hostRoot = process.cwd();
  const api = new KrixilApi(baseUrl);
  for (let attempt = 0; attempt < 3; attempt++) {
    const email = await prompt("Email: ");
    const password = await prompt("Password: ", true);
    if (!email || !password) {
      console.log("Email dan password wajib diisi.");
      continue;
    }
    try {
      let result;
      try {
        result = await api.login(tenantSlug, email, password);
      } catch (error) {
        if (!(error instanceof ApiError) || error.detail !== "2FA code required") throw error;
        const code = await prompt("Kode 2FA: ", true);
        result = await api.login(tenantSlug, email, password, code);
      }
      saveSession({ baseUrl, tenantSlug: result.tenantSlug, accessToken: result.accessToken, hostRoot });
      return { api, hostRoot };
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      console.log("Login gagal. Periksa akun, password, atau kode 2FA.");
    }
  }
  throw new Error("Login belum berhasil. Jalankan kirxil untuk mencoba lagi.");
}
