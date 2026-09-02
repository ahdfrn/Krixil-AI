/**
 * PRD §34's CLI Configuration — `.kirxil.yml`, discovered by walking up from the current
 * directory the same way `git` finds `.git` (so it applies anywhere inside a project, not only
 * at its exact root). Deliberately a small slice of the PRD's full example, not all of it:
 *
 * - `project.name` — cosmetic, shown in the interactive banner.
 * - `model.default` — which model to use when neither `--model` nor `/model` says otherwise.
 * - `agent.max_iterations` — an optional per-project step budget, forwarded as
 *   AgentRunRequest.max_steps. Only ever *tightens* the deployment's own ceiling
 *   (`settings.agent_max_steps`, see app/agents/service.py's create_agent_run) — a project can
 *   lower its own budget, never raise it, so this can't become a way to bypass the operator's
 *   configured resource limit.
 * - `verify` — an ordered list of real shell commands (`kirxil verify`, and `kirxil build`'s own
 *   tail — see verbs.ts) run for real, in order, stopping at the first real non-zero exit. Real
 *   CLI-native execution (execa, same as `kirxil doctor`/`checkpoint`/`git diff`), not routed
 *   through host.run_command/the agent — these are commands the user themselves configured and
 *   already trusts, not agent-generated ones, so gating each on a HIGH-risk approval pause would
 *   be friction with no real safety benefit.
 *
 * Deliberately NOT implemented here: `model.coding`/`model.reasoning` (routing by task type) —
 * this deployment only has two unbenchmarked local Ollama models, and picking one over the other
 * per task type with no real basis to justify the choice would be exactly the kind of fabricated
 * capability this project has avoided everywhere else (see app/ai/catalog.py's own "no fabricated
 * catalog entries" rule) — that's the user's own call to make and set via `model.default`, not
 * something to guess at. Also not implemented: `permissions:` (would mean a client-supplied YAML
 * file can loosen or tighten the Permission Engine's approval requirements — a real security
 * policy decision that deserves an explicit conversation, not something to wire in as a side
 * effect of "add a config file"), `sandbox:` (host.* is unsandboxed by design already), and
 * `memory:` (already a real per-*user* setting server-side, not a per-project one).
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, parse } from "node:path";
import { load } from "js-yaml";
import { z } from "zod";

const ProjectConfigSchema = z.object({
  project: z.object({ name: z.string().optional() }).optional(),
  model: z.object({ default: z.string().optional() }).optional(),
  agent: z.object({ max_iterations: z.number().int().positive().optional() }).optional(),
  verify: z.array(z.string().min(1)).optional(),
});

export type ProjectConfig = z.infer<typeof ProjectConfigSchema>;

/** Exposed separately from loadProjectConfig so `kirxil config` can show *where* a config came
 * from (or that none was found), not just its parsed values. */
export function findConfigFile(startDir: string = process.cwd()): string | null {
  let dir = startDir;
  for (;;) {
    const candidate = join(dir, ".kirxil.yml");
    if (existsSync(candidate)) return candidate;
    const parentDir = dirname(dir);
    if (parentDir === dir || dir === parse(dir).root) return null;
    dir = parentDir;
  }
}

/** Best-effort, like checkpoint.ts: no file, or a file that doesn't parse/validate, just means
 * "no project config" — never blocks the CLI from working, only warns so a typo isn't silent. */
export function loadProjectConfig(cwd: string = process.cwd()): ProjectConfig | null {
  const path = findConfigFile(cwd);
  if (!path) return null;
  let raw: unknown;
  try {
    raw = load(readFileSync(path, "utf-8"));
  } catch (err) {
    console.error(`Couldn't parse ${path}: ${err instanceof Error ? err.message : String(err)}`);
    return null;
  }
  const parsed = ProjectConfigSchema.safeParse(raw ?? {});
  if (!parsed.success) {
    console.error(
      `Ignoring ${path} — doesn't match the expected shape (project.name, model.default, ` +
        "agent.max_iterations, verify).",
    );
    return null;
  }
  return parsed.data;
}
