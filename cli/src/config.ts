/**
 * Credentials + local preferences — stored once via `kirxil login` so day-to-day use doesn't need
 * an env file. Falls back to KRIXIL_TENANT_SLUG/KRIXIL_EMAIL/KRIXIL_PASSWORD env vars if present
 * and no stored session exists, matching training/client.py's convention.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync, chmodSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { z } from "zod";

const CONFIG_DIR = join(homedir(), ".krixil");
const CREDENTIALS_PATH = join(CONFIG_DIR, "credentials.json");

const SessionSchema = z.object({
  baseUrl: z.string(),
  tenantSlug: z.string(),
  accessToken: z.string(),
  // The real, unsandboxed folder host.* tools operate under on the api service's machine (see
  // services/host-runner/.env's HOST_ROOT) — asked once at login so the CLI can compute a goal's
  // `dir` from wherever it's actually launched, the "operates where you're standing" feel a real
  // terminal coding agent has. Not enforced client-side; the real boundary is still
  // host-runner's own path confinement.
  hostRoot: z.string(),
});

export type Session = z.infer<typeof SessionSchema>;

export function loadSession(): Session | null {
  if (!existsSync(CREDENTIALS_PATH)) return null;
  try {
    const raw = JSON.parse(readFileSync(CREDENTIALS_PATH, "utf-8"));
    return SessionSchema.parse(raw);
  } catch {
    return null;
  }
}

export function saveSession(session: Session): void {
  if (!existsSync(CONFIG_DIR)) mkdirSync(CONFIG_DIR, { recursive: true });
  writeFileSync(CREDENTIALS_PATH, JSON.stringify(session, null, 2), "utf-8");
  // Best-effort — Windows ACLs don't honor chmod the way POSIX does, but this is still correct on
  // any POSIX machine this CLI runs on, and harmless where it's a no-op.
  try {
    chmodSync(CREDENTIALS_PATH, 0o600);
  } catch {
    // ignore
  }
}

export function clearSession(): void {
  if (existsSync(CREDENTIALS_PATH)) unlinkSync(CREDENTIALS_PATH);
}

export function envLogin(): { tenantSlug: string; email: string; password: string } | null {
  const tenantSlug = process.env.KRIXIL_TENANT_SLUG;
  const email = process.env.KRIXIL_EMAIL;
  const password = process.env.KRIXIL_PASSWORD;
  if (tenantSlug && email && password) return { tenantSlug, email, password };
  return null;
}

export const paths = { CONFIG_DIR, CREDENTIALS_PATH };
