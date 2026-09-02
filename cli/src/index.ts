#!/usr/bin/env node
/**
 * Entry point — `kirxil` (interactive), `kirxil run "<goal>"` (one-shot), `kirxil login`/`logout`,
 * `kirxil ask/explain/analyze/generate/refactor/debug/test/review/plan` (verbs.ts — same
 * pipeline as `run`, verb-specific instructions), `kirxil checkpoint`/`undo`, `kirxil memory
 * list/add/forget/status/on/off` (a real client of the existing app/memory/ backend, no new
 * backend surface), `kirxil doctor`, `kirxil config` (what .kirxil.yml actually resolves to
 * here), and local, real passthrough commands (`kirxil search`,
 * `kirxil git diff/status/log/branch/blame`) — see README.md. Talks to the same
 * services/ai-service backend the web app does — nothing here is a second implementation of the
 * agent loop, just another client of it.
 */

import { existsSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { Command } from "commander";
import { dump } from "js-yaml";
import { render } from "ink";
import React from "react";
import { execa } from "execa";
import { ApiError, KrixilApi, type ModelInfo } from "./api.js";
import { diffStatSinceCheckpoint, findLastCheckpoint, isGitRepo, manualCheckpoint, resetToBeforeCheckpoint } from "./checkpoint.js";
import { clearSession, envLogin, loadSession, saveSession } from "./config.js";
import { dirFromCwd } from "./goal.js";
import { isOnPath } from "./platform.js";
import { findConfigFile, loadProjectConfig } from "./projectConfig.js";
import { confirm, prompt } from "./prompt.js";
import { swarmChildStatusIcon } from "./render.js";
import { App } from "./ui/App.js";
import { buildVerbInstruction, VERBS } from "./verbs.js";
import { printVerifyResult, runVerifyPipeline } from "./verify.js";

const DEFAULT_BASE_URL = "http://localhost:8000/api/v1";
const NOT_LOGGED_IN = "Not logged in. Run `kirxil login` first, or set KRIXIL_TENANT_SLUG/KRIXIL_EMAIL/KRIXIL_PASSWORD.";

function resolveClient(): { api: KrixilApi; hostRoot: string } | null {
  const session = loadSession();
  if (session) return { api: new KrixilApi(session.baseUrl, session.accessToken), hostRoot: session.hostRoot };
  return null;
}

async function resolveClientOrEnv(): Promise<{ api: KrixilApi; hostRoot: string } | null> {
  const stored = resolveClient();
  if (stored) return stored;
  const env = envLogin();
  if (!env) return null;
  const api = new KrixilApi(DEFAULT_BASE_URL);
  try {
    await api.login(env.tenantSlug, env.email, env.password);
  } catch (err) {
    console.error(err instanceof ApiError ? `Login failed: ${err.detail}` : "Login failed.");
    process.exit(1);
  }
  // No interactive login happened to ask for a real HOST_ROOT — D:\ is this project's own real
  // default (services/host-runner/.env.example), overridable by running `kirxil login` instead.
  return { api, hostRoot: "D:\\" };
}

/** Same "resolve or bail with the same message" shape `models`/`run`/every verb already used
 * inline — pulled out once the `memory` subcommand group needed it six more times. */
async function requireApi(): Promise<KrixilApi> {
  const client = await resolveClientOrEnv();
  if (!client) {
    console.error(NOT_LOGGED_IN);
    process.exit(1);
  }
  return client.api;
}

/** `run` and every verb command (ask/explain/analyze/...) share this exact shape — resolve a
 * client or bail with the same message, then hand a goal to the same runOnce.ts pipeline.
 * modelOverride is undefined unless `--model` was actually typed — precedence is
 * `--model` > `.kirxil.yml`'s `model.default` (PRD §34) > "auto". `agent.max_iterations` from
 * the same file, if present, is forwarded as this run's step budget. */
async function runInstruction(
  instruction: string,
  dirOverride: string | undefined,
  modelOverride: string | undefined,
  runVerifyAfter = false,
): Promise<void> {
  const client = await resolveClientOrEnv();
  if (!client) {
    console.error(NOT_LOGGED_IN);
    process.exit(1);
  }
  const projectConfig = loadProjectConfig();
  const model = modelOverride ?? projectConfig?.model?.default ?? "auto";
  const maxSteps = projectConfig?.agent?.max_iterations;
  const { runGoalOnce } = await import("./runOnce.js");
  await runGoalOnce(
    client.api,
    instruction,
    dirOverride ?? dirFromCwd(client.hostRoot),
    model,
    maxSteps,
    undefined,
    runVerifyAfter,
  );
}

/** `kirxil plan <goal>` specifically — same pipeline as runInstruction, but keeps the raw goal
 * around (not just the verb-wrapped instruction) so a completed plan can offer a real
 * `kirxil build` handoff with that same goal (see runOnce.ts's PlanHandoff). */
async function runPlanInstruction(rawGoal: string, dirOverride: string | undefined, modelOverride: string | undefined): Promise<void> {
  const client = await resolveClientOrEnv();
  if (!client) {
    console.error(NOT_LOGGED_IN);
    process.exit(1);
  }
  const projectConfig = loadProjectConfig();
  const model = modelOverride ?? projectConfig?.model?.default ?? "auto";
  const maxSteps = projectConfig?.agent?.max_iterations;
  const instruction = buildVerbInstruction("plan", rawGoal);
  const { runGoalOnce } = await import("./runOnce.js");
  await runGoalOnce(client.api, instruction, dirOverride ?? dirFromCwd(client.hostRoot), model, maxSteps, { rawGoal });
}

const program = new Command();
program.name("kirxil").description("Kirxil AI — an autonomous software engineering agent in your terminal.");

program
  .command("login")
  .description("Log in once and remember the session in ~/.krixil/credentials.json.")
  .option("--base-url <url>", "Krixil api service base URL.", DEFAULT_BASE_URL)
  .action(async (opts: { baseUrl: string }) => {
    const tenantSlug = await prompt("Workspace slug: ");
    const email = await prompt("Email: ");
    const password = await prompt("Password: ", true);
    const hostRoot = await prompt("HOST_ROOT (see services/host-runner/.env, e.g. D:\\): ");

    const api = new KrixilApi(opts.baseUrl);
    try {
      const result = await api.login(tenantSlug, email, password);
      saveSession({ baseUrl: opts.baseUrl, tenantSlug: result.tenantSlug, accessToken: result.accessToken, hostRoot });
      console.log(`Logged in as ${result.tenantSlug}. Session saved to ~/.krixil/credentials.json.`);
    } catch (err) {
      console.error(err instanceof ApiError ? `Login failed: ${err.detail}` : "Login failed.");
      process.exit(1);
    }
  });

program
  .command("logout")
  .description("Forget the saved session.")
  .action(() => {
    clearSession();
    console.log("Logged out.");
  });

program
  .command("models")
  .description("List the models this backend currently offers.")
  .action(async () => {
    const api = await requireApi();
    try {
      const models = await api.listModels();
      for (const m of models) console.log(`${m.name} (${m.id}) — ${m.description}`);
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't list models.");
      process.exit(1);
    }
  });

program
  .command("sessions")
  .description("List past agent runs for this workspace, newest first (real GET /agents data).")
  .action(async () => {
    const api = await requireApi();
    try {
      const runs = await api.listRuns();
      if (runs.length === 0) {
        console.log("No runs yet.");
        return;
      }
      for (const r of runs) {
        console.log(`${r.id}  ${r.status.padEnd(16)}  ${new Date(r.created_at).toLocaleString()}\n  ${r.goal}\n`);
      }
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't list runs.");
      process.exitCode = 1;
    }
  });

program
  .command("swarm <goal>")
  .description(
    "PRD §27 Multi-Agent Swarm — a real model call decomposes the goal into independent " +
      "sub-tasks, each runs as a real, ordinary agent run concurrently, then one more real " +
      "model call synthesizes a combined report. Not fabricated named specialist agents — " +
      "every sub-task is the same general agent loop, differentiated only by its own real goal.",
  )
  .option("--model <id>", "Model id from `kirxil models`, or \"auto\".")
  .option("--max-subtasks <n>", "Maximum sub-tasks to decompose into (2-8, default 5).", (v) => Number.parseInt(v, 10))
  .action(async (goal: string, opts: { model?: string; maxSubtasks?: number }) => {
    const api = await requireApi();
    const projectConfig = loadProjectConfig();
    const model = opts.model ?? projectConfig?.model?.default ?? "auto";

    console.log(`› ${goal}\n`);
    let started;
    try {
      started = await api.runSwarm(goal, model, opts.maxSubtasks);
    } catch (err) {
      console.error(err instanceof ApiError ? `Couldn't start that swarm: ${err.detail}` : "Couldn't start that swarm.");
      process.exitCode = 1;
      return;
    }
    console.log("Decomposing into sub-tasks and running them in parallel...\n");

    const printedStatus = new Map<string, string>();
    for (;;) {
      let swarm;
      try {
        swarm = await api.getSwarmStatus(started.id);
      } catch (err) {
        console.error(err instanceof ApiError ? `Lost track of that swarm: ${err.detail}` : "Lost track of that swarm.");
        process.exitCode = 1;
        return;
      }
      for (const child of swarm.children) {
        if (printedStatus.get(child.id) !== child.status) {
          printedStatus.set(child.id, child.status);
          console.log(`${swarmChildStatusIcon(child.status)} ${child.goal} — ${child.status}`);
        }
      }
      if (swarm.status !== "running") {
        console.log("");
        if (swarm.status === "completed") {
          console.log(`${swarm.subtask_count} sub-tasks completed.\n`);
          console.log("SYNTHESIS");
          console.log(swarm.synthesis ?? "");
        } else {
          console.error(swarm.error_message ?? "Swarm failed.");
          process.exitCode = 1;
        }
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  });

const brainCmd = program
  .command("brain")
  .description(
    "PRD §13 Project Brain — real file/symbol indexing and real semantic search over the " +
      "current project, backed by pgvector. `kirxil brain index` builds/refreshes it; " +
      "`kirxil brain search \"<query>\"` searches by meaning, not just exact text.",
  );

brainCmd
  .command("index")
  .description("(Re)index the current directory — a fresh full index each time, not incremental.")
  .option("--dir <dir>", "Folder to index, relative to HOST_ROOT (default: current directory).")
  .action(async (opts: { dir?: string }) => {
    const client = await resolveClientOrEnv();
    if (!client) {
      console.error(NOT_LOGGED_IN);
      process.exitCode = 1;
      return;
    }
    const directory = opts.dir ?? dirFromCwd(client.hostRoot);
    console.log(`Indexing ${directory === "." ? "the current directory" : directory}...`);
    let started;
    try {
      started = await client.api.indexBrain(directory);
    } catch (err) {
      console.error(err instanceof ApiError ? `Couldn't start indexing: ${err.detail}` : "Couldn't start indexing.");
      process.exitCode = 1;
      return;
    }
    for (;;) {
      let run;
      try {
        run = await client.api.getBrainStatus();
      } catch (err) {
        console.error(err instanceof ApiError ? `Lost track of that index run: ${err.detail}` : "Lost track of that index run.");
        process.exitCode = 1;
        return;
      }
      if (!run || run.id !== started.id || run.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        continue;
      }
      if (run.status === "completed") {
        console.log(
          `Indexed ${run.file_count} file${run.file_count === 1 ? "" : "s"}, found ` +
            `${run.symbol_count} real symbol${run.symbol_count === 1 ? "" : "s"}, embedded ` +
            `${run.chunk_count} chunk${run.chunk_count === 1 ? "" : "s"}.`,
        );
      } else {
        console.error(run.error_message ?? "Indexing failed.");
        process.exitCode = 1;
      }
      return;
    }
  });

brainCmd
  .command("search <query>")
  .description("Real semantic search over the current real index (run `kirxil brain index` first).")
  .option("--limit <n>", "Maximum results (default 10).", (v) => Number.parseInt(v, 10))
  .action(async (query: string, opts: { limit?: number }) => {
    const api = await requireApi();
    try {
      const results = await api.searchBrain(query, opts.limit);
      if (results.length === 0) {
        console.log("No matches — have you run `kirxil brain index` yet?");
        return;
      }
      for (const r of results) {
        console.log(`${r.path}${r.language ? ` (${r.language})` : ""}`);
        const preview = r.content.slice(0, 200).replace(/\n/g, " ");
        console.log(`  ${preview}${r.content.length > 200 ? "…" : ""}\n`);
      }
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't search.");
      process.exitCode = 1;
    }
  });

const mcpCmd = program
  .command("mcp")
  .description(
    "PRD §10 MCP Hub — real, tenant-configured MCP (Model Context Protocol) servers (stdio " +
      "transport). `kirxil mcp add` configures one; the agent reaches it through the real " +
      "mcp.list_tools/mcp.call_tool tools (HIGH risk, approval-gated, same as host.run_command).",
  );

mcpCmd
  .command("add <name> <command> [args...]")
  .description(
    "Add a real MCP server, e.g. `kirxil mcp add fs npx -- -y @modelcontextprotocol/server-filesystem D:\\some\\path`.",
  )
  .option("--env <key=value>", "Environment variable to pass to the server (repeatable).", (val: string, prev: string[]) => [...prev, val], [] as string[])
  .action(async (name: string, command: string, args: string[], opts: { env: string[] }) => {
    const api = await requireApi();
    const env: Record<string, string> = {};
    for (const pair of opts.env) {
      const eq = pair.indexOf("=");
      if (eq === -1) {
        console.error(`Invalid --env value '${pair}' — expected KEY=VALUE.`);
        process.exitCode = 1;
        return;
      }
      env[pair.slice(0, eq)] = pair.slice(eq + 1);
    }
    try {
      const server = await api.addMcpServer(name, command, args, env);
      console.log(`Added '${server.name}' (${server.command} ${server.args.join(" ")}).`);
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't add that server.");
      process.exitCode = 1;
    }
  });

mcpCmd
  .command("list")
  .description("List this tenant's configured real MCP servers.")
  .action(async () => {
    const api = await requireApi();
    try {
      const servers = await api.listMcpServers();
      if (servers.length === 0) {
        console.log("No MCP servers configured yet — see `kirxil mcp add`.");
        return;
      }
      for (const s of servers) {
        const envPart = Object.keys(s.env).length > 0 ? ` env: ${Object.keys(s.env).join(", ")}` : "";
        console.log(`${s.name}  ${s.command} ${s.args.join(" ")}${envPart}`);
      }
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't list servers.");
      process.exitCode = 1;
    }
  });

mcpCmd
  .command("remove <name>")
  .description("Remove a configured MCP server by name.")
  .action(async (name: string) => {
    const api = await requireApi();
    try {
      const servers = await api.listMcpServers();
      const server = servers.find((s) => s.name === name);
      if (!server) {
        console.error(`No MCP server named '${name}'.`);
        process.exitCode = 1;
        return;
      }
      await api.removeMcpServer(server.id);
      console.log(`Removed '${name}'.`);
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't remove that server.");
      process.exitCode = 1;
    }
  });

mcpCmd
  .command("tools <name>")
  .description("Real, live connection to a configured server — lists whatever it actually advertises right now.")
  .action(async (name: string) => {
    const api = await requireApi();
    try {
      const servers = await api.listMcpServers();
      const server = servers.find((s) => s.name === name);
      if (!server) {
        console.error(`No MCP server named '${name}'.`);
        process.exitCode = 1;
        return;
      }
      const tools = await api.getMcpServerTools(server.id);
      if (tools.length === 0) {
        console.log(`'${name}' advertises no tools.`);
        return;
      }
      for (const t of tools) console.log(`${t.name}  —  ${t.description}`);
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't reach that server.");
      process.exitCode = 1;
    }
  });

program
  .command("run <goal>")
  .description("Run one goal and exit — for scripting, not the interactive feel of plain `kirxil`.")
  .option("--model <id>", "Model id from `kirxil models`, or \"auto\". Defaults to .kirxil.yml's model.default, else \"auto\".")
  .option("--dir <dir>", "Folder to work in, relative to HOST_ROOT (defaults to wherever this is launched from).")
  .action(async (goal: string, opts: { model?: string; dir?: string }) => {
    await runInstruction(goal, opts.dir, opts.model);
  });

// PRD §33's command surface (ask/explain/analyze/generate/refactor/debug/test/review) — each one
// is the same runInstruction() pipeline `run` uses, just with a verb-specific instruction built
// by verbs.ts instead of the raw goal text, so every one of these gets the live transcript, the
// Permission Engine pause, and the pre-run checkpoint for free.
for (const verb of VERBS) {
  program
    .command(`${verb.name} ${verb.argSyntax}`)
    .description(verb.description)
    .option("--model <id>", "Model id from `kirxil models`, or \"auto\". Defaults to .kirxil.yml's model.default, else \"auto\".")
    .option("--dir <dir>", "Folder to work in, relative to HOST_ROOT (defaults to wherever this is launched from).")
    .action(async (argument: string | undefined, opts: { model?: string; dir?: string }) => {
      // `plan` alone gets the bordered PLAN panel + real "run kirxil build with this goal now?"
      // handoff (runOnce.ts's PlanHandoff) — every other verb uses the plain shared pipeline.
      if (verb.name === "plan") {
        await runPlanInstruction(argument ?? "", opts.dir, opts.model);
        return;
      }
      const instruction = buildVerbInstruction(verb.name, argument ?? "");
      // `build` alone auto-runs .kirxil.yml's real `verify:` pipeline afterward (verify.ts) — a
      // real, deterministic check instead of trusting the model's own "Review" phase narration.
      await runInstruction(instruction, opts.dir, opts.model, verb.name === "build");
    });
}

const gitCmd = program.command("git").description("Real git passthrough, run locally where this CLI was launched (§28: Branches, Commits, Diff, Blame, History).");
gitCmd
  .command("diff")
  .description("`git diff` in the current directory.")
  .action(async () => {
    const { stdout } = await execa("git", ["diff"], { cwd: process.cwd(), reject: false });
    console.log(stdout || "(no changes)");
  });
gitCmd
  .command("status")
  .description("`git status` in the current directory.")
  .action(async () => {
    const { stdout } = await execa("git", ["status"], { cwd: process.cwd(), reject: false });
    console.log(stdout);
  });
gitCmd
  .command("log")
  .description("`git log` (one-line, last 20) in the current directory.")
  .action(async () => {
    const { stdout } = await execa("git", ["log", "--oneline", "-20"], { cwd: process.cwd(), reject: false });
    console.log(stdout || "(no commits)");
  });
gitCmd
  .command("branch")
  .description("`git branch` (all local branches) in the current directory.")
  .action(async () => {
    const { stdout } = await execa("git", ["branch"], { cwd: process.cwd(), reject: false });
    console.log(stdout || "(no branches)");
  });
gitCmd
  .command("blame <file>")
  .description("`git blame` a file in the current directory — who last touched each line.")
  .action(async (file: string) => {
    const result = await execa("git", ["blame", "--", file], { cwd: process.cwd(), reject: false });
    console.log(result.failed ? result.stderr || `Couldn't blame '${file}'.` : result.stdout);
  });

const memoryCmd = program
  .command("memory")
  .description("Long-term memory Krixil has picked up from your chats/runs (PRD §33) — the real backend under app/memory/.");
memoryCmd
  .command("list")
  .description("List everything currently remembered.")
  .action(async () => {
    const api = await requireApi();
    try {
      const memories = await api.listMemories();
      if (memories.length === 0) {
        console.log("Nothing remembered yet.");
        return;
      }
      for (const m of memories) console.log(`${m.id}  ${new Date(m.created_at).toLocaleString()}\n  ${m.content}\n`);
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't list memories.");
      process.exit(1);
    }
  });
memoryCmd
  .command("add <content>")
  .description("Remember something explicitly, rather than waiting for it to come up in a run.")
  .action(async (content: string) => {
    const api = await requireApi();
    try {
      const memory = await api.addMemory(content);
      console.log(`Remembered (${memory.id}).`);
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't add that memory.");
      process.exit(1);
    }
  });
memoryCmd
  .command("forget <id>")
  .description("Delete one remembered fact by its id (see `kirxil memory list`).")
  .action(async (id: string) => {
    const api = await requireApi();
    try {
      await api.forgetMemory(id);
      console.log("Forgotten.");
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't forget that memory.");
      process.exit(1);
    }
  });
memoryCmd
  .command("status")
  .description("Whether Krixil is currently allowed to remember things at all.")
  .action(async () => {
    const api = await requireApi();
    try {
      const enabled = await api.getMemorySettings();
      console.log(enabled ? "Memory is on." : "Memory is off.");
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't read memory settings.");
      process.exit(1);
    }
  });
memoryCmd
  .command("on")
  .description("Turn memory on.")
  .action(async () => {
    const api = await requireApi();
    await api.setMemorySettings(true);
    console.log("Memory is on.");
  });
memoryCmd
  .command("off")
  .description("Turn memory off.")
  .action(async () => {
    const api = await requireApi();
    await api.setMemorySettings(false);
    console.log("Memory is off.");
  });

program
  .command("doctor")
  .description("Check that everything kirxil needs is actually working.")
  .action(async () => {
    const lines: string[] = [];
    const session = loadSession();
    if (session) {
      lines.push(`✓ Logged in as ${session.tenantSlug} (${session.baseUrl})`);
      try {
        await new KrixilApi(session.baseUrl, session.accessToken).listModels();
        lines.push("✓ Backend reachable and responding.");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          lines.push("✗ Backend reachable, but this session is invalid or expired — run `kirxil login` again.");
        } else {
          lines.push(`✗ Backend not reachable: ${err instanceof ApiError ? err.detail : "unknown error"}`);
        }
      }
    } else if (envLogin()) {
      lines.push("○ Not logged in via `kirxil login`, but KRIXIL_TENANT_SLUG/EMAIL/PASSWORD are set — `kirxil run` will use those.");
    } else {
      lines.push("✗ Not logged in. Run `kirxil login`, or set KRIXIL_TENANT_SLUG/KRIXIL_EMAIL/KRIXIL_PASSWORD.");
    }

    lines.push((await isOnPath("git")) ? "✓ git is on PATH." : "✗ git isn't on PATH — checkpoints and `kirxil git ...` won't work.");
    lines.push(
      (await isGitRepo(process.cwd()))
        ? "✓ Current directory is a git repo — checkpoints/undo will work here."
        : "○ Current directory isn't a git repo — checkpoints/undo won't do anything here.",
    );
    lines.push(
      (await isOnPath("rg"))
        ? "✓ ripgrep (rg) is on PATH."
        : "○ ripgrep (rg) isn't on PATH — `kirxil search` won't work (optional).",
    );
    lines.push('○ host-runner reachability can\'t be checked directly from here — try `kirxil run "list files here"` to confirm it.');

    console.log(lines.join("\n"));
  });

program
  .command("config")
  .description("Show the resolved .kirxil.yml for the current directory, and what's actually in effect (PRD §34).")
  .action(() => {
    const path = findConfigFile();
    if (!path) {
      console.log(
        "No .kirxil.yml found (looked here and every parent directory up to the filesystem root).\n\n" +
          "In effect:\n" +
          "  project.name          (not set — folder name shown instead)\n" +
          '  model.default         (not set — "auto" used instead)\n' +
          "  agent.max_iterations  (not set — this deployment's own default step budget used instead)\n" +
          "  verify                (not set — `kirxil verify`/`kirxil build` have nothing to run)\n\n" +
          "See cli/README.md's \"Project config\" section for the format.",
      );
      return;
    }
    const config = loadProjectConfig();
    console.log(`Config file: ${path}\n`);
    if (!config) {
      // loadProjectConfig() already printed exactly why (invalid YAML, or doesn't match the
      // expected shape) — nothing useful to add here beyond confirming where it looked.
      return;
    }
    console.log("In effect:");
    console.log(`  project.name          = ${config.project?.name ?? "(not set — folder name shown instead)"}`);
    console.log(`  model.default         = ${config.model?.default ?? '(not set — "auto" used instead)'}`);
    console.log(
      `  agent.max_iterations  = ${config.agent?.max_iterations ?? "(not set — this deployment's own default step budget used instead)"}`,
    );
    console.log(
      `  verify                = ${config.verify && config.verify.length > 0 ? config.verify.join(" && ") : "(not set — `kirxil verify`/`kirxil build` have nothing to run)"}`,
    );
  });

program
  .command("init")
  .description("Interactively scaffold a .kirxil.yml for the current directory (PRD §34).")
  .action(async () => {
    const targetPath = join(process.cwd(), ".kirxil.yml");
    if (existsSync(targetPath)) {
      const overwrite = await confirm(`${targetPath} already exists — overwrite it?`);
      if (!overwrite) {
        console.log("Cancelled — nothing changed.");
        return;
      }
    }

    const defaultName = basename(process.cwd());
    const projectName = (await prompt(`Project name [${defaultName}]: `)) || defaultName;

    const api = await requireApi();
    let models: ModelInfo[] = [];
    try {
      models = await api.listModels();
    } catch (err) {
      console.error(err instanceof ApiError ? err.detail : "Couldn't list models — leaving model.default unset.");
    }
    let modelDefault: string | undefined;
    if (models.length > 0) {
      console.log("\nAvailable models:");
      for (const m of models) console.log(`  ${m.id} — ${m.name}`);
      const chosen = await prompt('model.default (blank for "auto"): ');
      modelDefault = chosen || undefined;
    }

    const maxIterationsRaw = await prompt("agent.max_iterations (blank to use this deployment's own default budget): ");
    let maxIterations: number | undefined;
    if (maxIterationsRaw.trim()) {
      const parsed = Number(maxIterationsRaw.trim());
      if (Number.isInteger(parsed) && parsed > 0) {
        maxIterations = parsed;
      } else {
        console.error("agent.max_iterations must be a positive whole number — leaving it unset.");
      }
    }

    const config: Record<string, unknown> = { project: { name: projectName } };
    if (modelDefault) config.model = { default: modelDefault };
    if (maxIterations) config.agent = { max_iterations: maxIterations };

    writeFileSync(targetPath, dump(config));
    console.log(`\nWrote ${targetPath}. Run \`kirxil config\` to see it resolved.`);
  });

program
  .command("search <pattern>")
  .description("Search the current directory with ripgrep (must be installed and on PATH).")
  .action(async (pattern: string) => {
    // Checked as a separate, explicit step rather than inferred from `rg`'s own exit code —
    // real bug, caught live: on Windows, execa/cross-spawn falls back to cmd.exe for an
    // unresolvable binary, which prints "'rg' is not recognized..." and exits 1 — the exact same
    // `.failed`/exitCode shape as ripgrep's own documented "ran fine, zero matches" exit code.
    // The two are genuinely indistinguishable from the result object alone (no ENOENT surfaces
    // through execa on this platform either), so the previous version of this check — reading
    // `.failed` off the search itself — reported "isn't installed" on every real zero-match
    // search too, not just when `rg` was actually missing.
    if (!(await isOnPath("rg"))) {
      console.error("ripgrep (`rg`) isn't installed or isn't on PATH.");
      process.exitCode = 1;
      return;
    }
    const result = await execa("rg", ["--line-number", "--color", "never", pattern], {
      cwd: process.cwd(),
      reject: false,
    });
    // ripgrep's own exit code 1 means "ran fine, zero matches" — not an error either.
    console.log(result.stdout || "No matches.");
  });

program
  .command("checkpoint [message]")
  .description("Snapshot the current directory with git (git add -A && commit), so `kirxil undo` can get back to it.")
  .action(async (message?: string) => {
    const result = await manualCheckpoint(process.cwd(), message);
    if (result.ok) {
      console.log(`Checkpointed (${result.hash}).`);
    } else {
      console.error(result.reason);
      process.exitCode = 1;
    }
  });

program
  .command("undo")
  .description("Revert to the most recent kirxil checkpoint in this directory (git reset --hard — asks first).")
  .action(async () => {
    const cwd = process.cwd();
    const checkpoint = await findLastCheckpoint(cwd);
    if (!checkpoint) {
      console.error("No kirxil checkpoint found here — run `kirxil checkpoint` or a goal first.");
      process.exitCode = 1;
      return;
    }
    const stat = await diffStatSinceCheckpoint(cwd, checkpoint);
    if (!stat.trim()) {
      console.log("Nothing has changed since the last checkpoint.");
      return;
    }
    console.log("This will permanently discard:\n");
    console.log(stat);
    const approved = await confirm("Reset to right before that checkpoint?");
    if (!approved) {
      console.log("Cancelled — nothing changed.");
      return;
    }
    const result = await resetToBeforeCheckpoint(cwd, checkpoint);
    if (result.ok) {
      console.log("Reverted.");
    } else {
      console.error(result.reason);
      process.exitCode = 1;
    }
  });

program
  .command("verify")
  .description(
    "Run .kirxil.yml's `verify:` list for real, in order, stopping at the first real failure " +
      "(PRD §13's Verification Engine — real commands, not a model's own narrated claim).",
  )
  .action(async () => {
    const steps = loadProjectConfig()?.verify;
    if (!steps || steps.length === 0) {
      console.log(
        "No `verify:` list in .kirxil.yml — nothing to run. Add one, e.g.:\n\n" +
          "verify:\n  - npm run typecheck\n  - npm run lint\n  - npm test\n  - npm run build",
      );
      return;
    }
    const result = await runVerifyPipeline(steps, process.cwd());
    printVerifyResult(result);
    process.exitCode = result.allPassed ? 0 : 1;
  });

program.action(async () => {
  // The interactive REPL needs raw-mode-capable stdin (Ink's useInput, for Ctrl+C-to-cancel) —
  // a real terminal, not a pipe or redirect. Caught live: piping input into this crashed with a
  // raw React error-boundary stack trace instead of a clear message. `kirxil run "<goal>"`
  // (runOnce.ts, no Ink) is the documented path for scripted/piped use instead.
  if (!process.stdin.isTTY) {
    console.error(
      "Interactive mode needs a real terminal (this stdin isn't one — piped or redirected input " +
        'isn\'t supported here). For scripted or piped use, run `kirxil run "<goal>"` instead.',
    );
    process.exit(1);
  }
  const client = await resolveClientOrEnv();
  if (!client) {
    console.error(NOT_LOGGED_IN);
    process.exit(1);
  }
  const initialDir = dirFromCwd(client.hostRoot);
  const projectConfig = loadProjectConfig();
  render(
    React.createElement(App, {
      api: client.api,
      hostRoot: client.hostRoot,
      initialDir,
      initialModel: projectConfig?.model?.default,
      maxSteps: projectConfig?.agent?.max_iterations,
      projectName: projectConfig?.project?.name,
    }),
    { exitOnCtrlC: false },
  );
});

program.parseAsync(process.argv);
