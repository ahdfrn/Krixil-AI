/** This package's own real version (`package.json`'s `version` field) — read at runtime instead
 * of hardcoded, so the banner never silently drifts from what's actually installed. Resolved
 * relative to this module's own compiled location (one level below the package root in both
 * `dist/` and `src/` via `tsx`), not `process.cwd()`, so it's correct regardless of which
 * directory `kirxil` is launched from. */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

function readVersion(): string {
  try {
    const here = dirname(fileURLToPath(import.meta.url));
    const pkg = JSON.parse(readFileSync(join(here, "..", "package.json"), "utf-8")) as { version?: string };
    return pkg.version ?? "0.0.0";
  } catch {
    return "0.0.0";
  }
}

export const VERSION = readVersion();
