/**
 * Builds the same advisory goal-framing shape apps/web/.../code/page.tsx's buildCodeGoal() (and
 * cli-python/krixil_cli/goal.py before it) uses — always the host.* tools (real, unsandboxed
 * access), scoped to whichever folder this CLI is launched from.
 */

import { isAbsolute, resolve, relative, sep } from "node:path";

const TOOLS =
  "host.list_files, host.read_file, host.write_file, host.edit_file, host.search_files, " +
  "host.delete_file, host.run_command";

export function buildGoal(instruction: string, dir: string): string {
  if (dir === ".") {
    return `Using your ${TOOLS} tools, work in the real folder on this machine. Task: ${instruction}`;
  }
  return (
    `Using your ${TOOLS} tools, work within the "${dir}" folder of the real folder on this ` +
    `machine. File paths are relative to the root, so prefix paths with "${dir}/" (e.g. ` +
    `"${dir}/main.py"). host.run_command already takes a separate "directory" argument for this ` +
    `— pass "${dir}" as that argument, and do not also \`cd\` into it from within the command ` +
    `string itself (that double-applies the folder and fails with a not-found error). Task: ${instruction}`
  );
}

/**
 * The folder this CLI was launched from, expressed relative to hostRoot the same way the web
 * app's Code page addresses one — "." if launched at hostRoot itself, a forward-slash relative
 * path otherwise, or "." if launched somewhere outside hostRoot entirely, since host.* tools
 * can't reach there regardless of what this function returns.
 */
export function dirFromCwd(hostRoot: string, cwd: string = process.cwd()): string {
  const resolvedRoot = resolve(hostRoot);
  const resolvedCwd = resolve(cwd);
  const rel = relative(resolvedRoot, resolvedCwd);
  if (rel === "") return ".";
  // Real bug, caught by a test: on Windows, path.relative() between two different drives (e.g.
  // hostRoot on D:\, cwd on E:\) can't express a true relative path, so it returns `to` back
  // basically unchanged — which does NOT start with ".." the way an ordinary "outside the tree"
  // case does. isAbsolute() catches that case too, not just the leading-".." one.
  if (rel.startsWith("..") || rel.startsWith(sep) || isAbsolute(rel)) return ".";
  // Windows path separators need normalizing to match the web app's forward-slash convention.
  return rel.split(sep).join("/");
}
