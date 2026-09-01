/**
 * Whether a binary is actually resolvable on PATH — checked explicitly via `where`/`which`
 * rather than inferred from running it, because on Windows execa/cross-spawn falls back to
 * `cmd.exe` for an unresolvable command, which exits 1 exactly like a real command's own
 * legitimate non-zero exit (see `kirxil search`'s history in docs/architecture/coding-agent.md —
 * that ambiguity is a real, previously-live bug, not a hypothetical one). Shared by `search` and
 * `doctor`, which both need to answer "is this actually here" honestly.
 */

import { execa } from "execa";

export async function isOnPath(binary: string): Promise<boolean> {
  const probe = process.platform === "win32" ? execa("where", [binary], { reject: false }) : execa("which", [binary], { reject: false });
  return !(await probe).failed;
}
