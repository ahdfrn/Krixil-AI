# kirxil — Kirxil AI CLI

An autonomous software engineering agent in your terminal — the CLI product defined in
[`docs/architecture/kirxil-cli-prd.md`](../docs/architecture/kirxil-cli-prd.md) (the user's own
PRD, reproduced there for reference). This is **Phase 1 (CLI Runtime) + a slice of the MVP scope**
from that PRD's own recommended build order (§50) — not the full platform (multi-agent
orchestrator, Project Brain, self-healing loop, visual/browser agents, plugin ecosystem, etc. are
later phases, not built yet). See
[`docs/architecture/coding-agent.md`](../docs/architecture/coding-agent.md) for the honest
done/not-done breakdown against the PRD.

Talks to the same `services/ai-service` backend the web app's Code page uses — same tools, same
live `⏺ Tool(args)` / `⎿ result` transcript, same real, unsandboxed access to whatever folder you
launch it from (via `services/host-runner`). Node.js + TypeScript + Ink (the PRD's own suggested
CLI stack), replacing an earlier working Python version kept at `../cli-python/` for reference.

## Setup

```powershell
cd cli
npm install
npm run build
npm link          # installs the real `kirxil` (and `krixil`) command globally
```

`services/ai-service` (Docker) and `services/host-runner` (native — see its own README) both need
to be running.

## Start / log in

```powershell
cd D:\some\real\project
kirxil
```

`kirxil` uses the current terminal directory and opens the CLI immediately when the saved
session is valid. Missing or expired sessions prompt for email and hidden password, then open
the CLI automatically. Passwords are never saved; 2FA is prompted when required.
On a fresh setup only, the account's workspace slug is requested (or set `KRIXIL_TENANT_SLUG`).
The current project folder is selected automatically, including projects outside the old
`HOST_ROOT`. No manual folder limit is required. `KRIXIL_BASE_URL` optionally changes the server.
Selection is available to the deployment owner and validated on the local host-runner, which
must run on the same computer as the CLI. Drive roots, home folders, and system roots are rejected.
The selected root is persisted per agent run and tool execution, including approval/resume.
File operations cannot traverse outside it; shell commands still run unsandboxed after approval.
Currently project-scoped sessions support the native runtime and host tools only; Hermes,
Swarm, and Brain indexing fail explicitly until they support the same scope.
Network failures do not
erase the saved session or trigger unnecessary login. `kirxil login` explicitly replaces a session.
The session is saved to `~/.krixil/credentials.json`. For
scripted/non-interactive use, set `KRIXIL_TENANT_SLUG`/`KRIXIL_EMAIL`/`KRIXIL_PASSWORD` instead
(same three variables `training/client.py` already reads).

## Use it

```powershell
cd D:\some\real\project
kirxil
```

```
██╗  ██╗██╗██████╗ ██╗  ██╗██╗██╗
██║ ██╔╝██║██╔══██╗╚██╗██╔╝██║██║
█████╔╝ ██║██████╔╝ ╚███╔╝ ██║██║
██╔═██╗ ██║██╔══██╗ ██╔██╗ ██║██║
██║  ██╗██║██║  ██║██╔╝ ██╗██║███████╗
╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝

v0.1.0                       ● online

Project some-real-project
Branch  main
Model   auto
128 files, 14 folders here

Working in . under D:\. /help for commands, /exit to quit.

> fix the bug where it crashes on empty input

⏺ Read(app.py)
  ⎿ Read 42 lines
⏺ Edit(app.py)
  ⎿ Edited (+3/-1)
     - if not values:
     + if not values:
     +     return None
     + # guard the empty-input case
⏺ Bash(pytest -q)
  ⎿ Paused for approval

╭ ⏸ Bash(pytest -q) ────────────────────────────╮
│ Risk: HIGH                                     │
│ HIGH risk — approve to run it for real, or     │
│ reject to stop this goal.                      │
│ Press y to approve, n to reject.               │
╰─────────────────────────────────────────────────╯
y

  ⎿ Exit 0
     3 passed in 0.41s

Fixed — the empty-input case now returns early instead of indexing into an empty list.

╭──────────────────────────────────────────────────╮
│ >                                                 │
╰──────────────────────────────────────────────────╯
╭──────────────────────────────────────────────────╮
│ 1 tool call · tests ✓ (passing) · +3/-1    /help /model /cwd /expand /undo /exit │
╰──────────────────────────────────────────────────╯
```

Requires a real terminal (raw-mode stdin, for `Ctrl+C`-to-cancel) — piped/redirected input prints
a clear message and exits rather than crashing. `Ctrl+C` stops a run in progress the same way the
web app's "esc to interrupt" does; `/model [id]` lists or switches models, `/cwd` shows the current
folder, `/plan <goal>` shows a read-only plan in a bordered panel with a real handoff into
`kirxil build`, `/undo` reverts to the last checkpoint, `/exit` quits. A persistent status bar at
the bottom shows the real tool-call count, the real self-healing pass/fail sequence (if any test
attempts happened), and real `git diff --stat`-derived change stats for the run in progress.

Any tool output over 40 lines is clipped by default (`… and N more lines`) — that content was
never printed at all, not just scrolled off-screen. `/expand` toggles the last run between clipped
and full output; running it again re-clips.

`↑`/`↓` recall previously submitted goals and `/commands`, real shell-history style — editing a
recalled line and pressing `↑` again starts back from the newest entry rather than jumping into
unrelated history. `Ctrl+L` clears this screen's visible run history (Ink appends to your
terminal's normal scrollback rather than taking over an alt-screen, so this can only clear what
this app itself has drawn, not your terminal's own history above it).

Deliberately not built here: a `Ctrl+K` command palette (there are only 6 real slash commands —
a searchable overlay would be decorative for that few, not genuinely useful) and `Tab`-style panel
navigation or a dedicated "agent panel" (this UI doesn't have multiple panels or a persistent
per-agent view to navigate between outside of `kirxil swarm`'s own tree, which already has its own
command).

### Command surface (PRD §33)

`kirxil run "<goal>"` is the general-purpose one, but the PRD also names specific verbs — these
are the same `runOnce.ts` pipeline underneath (same live transcript, same Permission Engine pause,
same pre-run checkpoint), just with a verb-specific instruction template (`cli/src/verbs.ts`)
instead of a raw goal string:

```powershell
kirxil ask "how does auth work in this repo?"       # read-only Q&A
kirxil explain app/agents/runner.py                  # read-only
kirxil analyze                                       # read-only, whole project by default
kirxil review                                        # read-only — reviews `git diff`, tags findings HIGH/MEDIUM/LOW
kirxil plan "add subscription billing"               # read-only — PLAN + numbered steps + a rough estimate, no execution
kirxil generate "a rate limiter middleware"
kirxil refactor app/utils/parsing.py
kirxil debug "login redirects to a blank page after 2FA"
kirxil test app/tools/host_tools.py
kirxil build "add a rate limiter middleware, tests included"  # PRD §20 — Plan, Implement, Test, Review in one run
```

The five read-only ones (`ask`, `explain`, `analyze`, `review`, `plan`) tell the model explicitly
not to create, edit, or delete anything — real instruction text, not a separate enforcement
mechanism, so it's asking the model to behave, not guaranteeing it (same trust model as every
other goal). `kirxil build` (PRD §20) is the one that actually does all four phases itself in one
run, including fixing and re-running a genuinely failing test rather than just reporting it — see
"Self-Healing & Verification" below for the two real, bounded mechanics behind that.

`kirxil plan "<goal>"` (PRD §19) is the one exception with its own presentation: it stops after
producing the plan (no auto-execute), but shows the model's real plan text in a bordered
`KIRXIL PLAN` panel and — in a real terminal only, never when piped/scripted — then offers a real
follow-up: press Enter to immediately run `kirxil build` with that exact same goal, or type
anything else to skip. This is genuine chaining of two commands that already exist independently,
not a new planning engine; `/plan <goal>` does the same thing inside the interactive REPL.

### Memory (PRD §33)

`kirxil memory list/add/forget/status/on/off` — a real terminal client of the memory system that
already existed (`app/memory/`, built well before this CLI track): durable, per-user facts
auto-extracted from completed chat/agent turns, the same ones the web app already surfaces. No
new backend surface, just the first way to reach it from a terminal instead of only the browser.

```powershell
kirxil memory list                                   # everything currently remembered
kirxil memory add "Prefers PowerShell examples, not bash."
kirxil memory forget <id>                             # id from `kirxil memory list`
kirxil memory status                                  # on or off
kirxil memory off                                     # stop remembering new things
```

### Self-Healing & Verification (PRD §22)

Two real, bounded mechanics behind `kirxil build`, replacing what used to be pure prompt text with
no enforcement:

- **Self-Healing** — a real, server-side `MAX_RETRIES` (`AGENT_MAX_TEST_RETRIES`, default 3):
  `app/agents/runner.py` counts real test-command attempts (`host.run_command`/`code.run_command`
  whose command looks like a test invocation) across the whole run — including across a HIGH-risk
  approval pause, since `host.run_command` always pauses, so every real attempt does too. Once a
  test attempt both fails and uses up the last retry, the run stops itself with an honest message
  naming the real attempt count and the real last failure, instead of silently retrying forever on
  the generic step budget or claiming success it didn't earn. The real pass/fail sequence is
  visible as it happens — the persistent status bar and each run's own summary line show it as
  `tests ✗ ✗ ✓ (passing)`, one real mark per attempt, read from that attempt's own observation
  (`render.ts`'s `testAttemptOutcomes`) — not a fabricated named state machine, since the backend
  doesn't tag steps with phase labels like "diagnosing" or "fixing" to draw one from honestly.
- **Verification** — a real, project-configurable pipeline: `.kirxil.yml`'s `verify:` list (see
  below) runs for real, in order, via `kirxil verify` or automatically after `kirxil build`
  completes — stopping at the first real non-zero exit, reporting the real output. Deliberately
  *not* routed through the agent/`host.run_command` — these are commands you configured yourself
  and already trust, so gating each on an approval pause would be friction with no real safety
  benefit.

```powershell
kirxil verify   # runs .kirxil.yml's verify: list standalone, stops at the first real failure
```

### Multi-Agent Swarm (PRD §27)

`kirxil swarm "<goal>"` — real decomposition, real parallel sub-agents, not fabricated named
specialists. One real model call breaks the goal into 2–8 independent sub-tasks; each becomes an
ordinary agent run (the exact same loop `kirxil run` uses) executed concurrently; one more real
model call combines every sub-task's actual outcome into a report, honestly naming anything that
failed. There's no separate Architect/Backend/Security "agent" — every sub-task is differentiated
only by its own real goal text.

```powershell
kirxil swarm "make this application production ready" --max-subtasks 5
```

```
› make this application production ready

Decomposing into sub-tasks and running them in parallel...

◉ Set up application logging and monitoring tools — running
◉ Implement database connection pooling and error handling — running
✓ Implement database connection pooling and error handling — completed
✓ Set up application logging and monitoring tools — completed

2 sub-tasks completed.

SYNTHESIS
...
```

If decomposition doesn't produce at least 2 real sub-tasks — the model's response doesn't parse
as a clean JSON array — the run fails honestly with a clear message rather than fabricating
sub-tasks or silently running the goal as a single-member "swarm." Not built: dependency-aware
sequencing between sub-tasks (every one runs independently; there's no "wait for this other
sub-task's result first" yet).

In a real terminal (not piped/redirected), `kirxil swarm` draws a live orchestrator tree instead
of the append-only log above — one real branch per sub-task, redrawn in place as each child's own
status and tool-call count change (`GET /agents/swarm/{id}/status`'s `children` are full,
individually-pollable `AgentRun`s, not a lightweight fabricated summary):

```
› make this application production ready

◉ ORCHESTRATOR — 2 sub-tasks
  ├─ ✓ Set up application logging and monitoring tools (6 tool calls — completed)
  └─ ✓ Implement database connection pooling and error handling (4 tool calls — completed)

SYNTHESIS
...
```

The plain log stays the scripted/piped fallback (`kirxil swarm ... > log.txt` still works exactly
as before) — same TTY-vs-pipe split `kirxil run` already has between the interactive REPL and
`runOnce.ts`.

### Project Brain (PRD §13)

`kirxil brain index` builds a real, searchable index of the current project — real file walk,
real Python symbol extraction (stdlib `ast`, real line numbers), a real but narrow JS/TS
regex-heuristic symbol scan (declaration line only, no fabricated block boundaries), real content
chunking and embeddings, stored in a real pgvector table. `kirxil brain search "<query>"` then
searches by real meaning, not just exact text — a query like "how do we charge a customer's
credit card" finds the function that actually does that even with no literal keyword overlap. A
new agent-callable `brain.search` tool means the model itself can use this mid-run too, not just
you from the CLI.

```powershell
kirxil brain index
# Indexing the current directory...
# Indexed 42 files, found 187 real symbols, embedded 96 chunks.

kirxil brain search "where do we validate the webhook signature"
# app/webhooks/verify.py (python)
#   def verify_signature(payload, signature, secret): ...
```

Each `kirxil brain index` run replaces the previous index outright — a fresh full re-index, not
incremental (there's no dependency tracking yet to know what actually changed). Not built:
Dependency Graph, API Map, Database Map, real Git History — separate, much bigger subsystems, not
attempted rather than faked. Indexing is scoped to the real `host.*`/HOST_ROOT tree only, not the
sandboxed `code.*` workspace.

### MCP Hub (PRD §16)

`kirxil mcp add <name> <command> [args...] [--env KEY=VALUE ...]` registers a real MCP (Model
Context Protocol) server for your tenant — a real local subprocess started over stdio, using the
official `mcp` SDK under the hood, not a hand-rolled client. Once added, the agent can see and use
that server's real tools mid-run (`mcp.list_servers`, `mcp.list_tools`, and an approval-gated
`mcp.call_tool` — same HIGH-risk pause/approve flow as `host.run_command`).

```powershell
kirxil mcp add local-tools python ./my_mcp_server.py
kirxil mcp list
# local-tools  python ./my_mcp_server.py

kirxil mcp tools local-tools
# add(a, b) — Add two real numbers.
# fail() — Always raises, to exercise the real error path.

kirxil mcp remove local-tools
```

Server `env` values are write-only — every response redacts them (`***`), so secrets you pass in
never round-trip back out through the API. Stdio transport only right now (a real local
subprocess you control the command for); no remote HTTP/SSE MCP servers yet. **Real limitation**:
the deployed `api` container has no Node.js/npx installed, so npx-based MCP servers (the most
common kind in the wild, e.g. `@modelcontextprotocol/server-filesystem`) can't actually be run
against this deployment yet — only Python-based (or otherwise container-available) server
commands work today.

### Project config — `.kirxil.yml` (PRD §34)

A small, deliberately narrow slice of the PRD's full config shape, discovered by walking up from
the current directory the way `git` finds `.git` (so it applies from any subfolder of a project):

```yaml
project:
  name: My Project        # shown in the interactive banner instead of the folder name
model:
  default: qwen2.5:7b     # used unless --model/  /model says otherwise
agent:
  max_iterations: 10      # this project's own step budget — can only be *tighter* than the
                           # deployment's own ceiling (agent_max_steps), never looser
verify:                   # real shell commands, run in order, stopping at the first real failure
  - npm run typecheck     # (see "Self-Healing & Verification" above) — `kirxil verify`, and
  - npm run lint          # `kirxil build`'s own automatic tail
  - npm test
  - npm run build
```

Precedence for the model: `--model`/`/model` > `.kirxil.yml`'s `model.default` > `"auto"`. Not
implemented: `model.coding`/`model.reasoning` (task-based auto-routing — see below),
`agent.max_retries`, `permissions:`, `sandbox:`, `memory:` — see `docs/architecture/
kirxil-cli-prd.md`'s §34 status note for why each one specifically isn't built yet.

`kirxil config` shows what's actually resolved — which file it found (if any) and each field's
effective value, with a plain fallback description when something isn't set, rather than leaving
you to guess whether `.kirxil.yml` is even being picked up:

```powershell
kirxil config
# Config file: D:\some\project\.kirxil.yml
#
# In effect:
#   project.name          = My Project
#   model.default         = qwen2.5:7b
#   agent.max_iterations  = 10
```

### Model Router (PRD §30)

Model-agnostic selection is real (`/model`, `--model`, `.kirxil.yml`'s `model.default`), but
automatic routing *by task type* (Reasoning/Coding/Fast/Vision/Local) is not — no benchmark
distinguishes which configured provider/model is better at what, so inventing that mapping would
be a fabricated capability, not a real one. Pick your own default with `model.default` instead.

The backend's `MODEL_PROVIDER` (`services/ai-service/.env`) currently has real code for six
providers: `mock`, `openai` (any OpenAI-compatible endpoint), `ollama` (this deployment's real
default), `anthropic`, `openrouter`, and `groq` — the last two genuinely OpenAI-compatible for
both chat and embeddings — plus `huggingface` (chat-only compatible; its embeddings always
delegate to Ollama's). `kirxil models` lists whatever the currently-active one actually offers.
Only `anthropic`/`openrouter`/`groq`/`huggingface` have real, tested-against-mocked-HTTP code but
**no live verification against a real vendor API** — none of this CLI's sessions have had a real
key for any of them. Real code, unconfirmed live behavior, same honest caveat every time until
someone supplies a real key.

### AgentRuntime — native vs. Hermes

Every run's AI reasoning normally happens via `services/ai-service`'s own native agent loop
(`runtime=native`, the default). `--runtime hermes` (`kirxil run`, every verb, or the bare
interactive REPL; `.kirxil.yml`'s `agent.runtime` sets the project default, same precedence shape
as `--model`/`model.default`) proxies the run instead to a real, separately-run
[Hermes](https://github.com/NousResearch/hermes-agent) instance over its own documented HTTP+SSE
"Runs API" — Hermes is never imported into this backend as a dependency (its own exact-pinned
`pydantic`/`httpx` genuinely conflict with this service's pins), so it runs as its own service,
configured via `HERMES_BASE_URL`/`HERMES_API_KEY` (`services/ai-service/.env`). Requesting
`runtime=hermes` with no `HERMES_BASE_URL` configured fails with a clear error, never a silent
fallback to native. A Hermes-originated tool call still always resolves through this same CLI's
real Permission Engine (below) — same approve/reject prompt, same audit log — Hermes is never a
second, parallel approval system. See `docs/architecture/hermes-runtime.md` for the full design.

### Permission Engine (PRD §17)

Reading, listing, and searching files runs immediately (LOW risk). Writing or editing a file runs
immediately too (MEDIUM — a deliberate choice, see `services/ai-service/app/tools/host_tools.py`).
Deleting a file or running a shell command is HIGH risk — the run pauses in a bordered panel
showing the exact tool call and its risk level, and waits for a real `y`/`n` before `host-runner`
ever sees it (`n` stops that goal for good). Approving doesn't just run that one action and quit,
either — the agent picks the conversation back up and keeps working, the same way it would if
nothing had paused. Nothing registered above HIGH exists in `host.*`/`code.*` today, but if a
CRITICAL-risk tool is ever added, the same panel asks for a real typed `CONFIRM` instead of a
single keypress — a real, generic mechanism, not tied to any particular tool. This isn't
CLI-side theater: the pause, the risk tiers, and the approve/reject endpoints all live in the
backend (`app/tools/service.py`, `app/agents/runner.py`) and are the same ones the web app's
Agents/Tools pages already used for other tools (`document.delete`, etc.) — this just extends
that same real mechanism to `host.*`/`code.*` and wires the CLI to it. Not built: an "always
allow for project/session" option — that needs new backend policy storage (remembering a decision
across executions), a real security-relevant scope decision on its own, not bundled into a visual
pass.

A real BLOCK tier also exists now, above HIGH: `host.run_command`/`code.run_command`'s actual
command text is checked against a narrow, documented pattern list
(`services/ai-service/app/tools/risk_rules.py`) — recursive force-delete of `/`, formatting or
recursively deleting a whole Windows drive, writing/reformatting a raw disk device — before the
approval pause above ever runs. A match never reaches a `y`/`n` prompt at all; the transcript shows
`🚫 Blocked` with the real reason instead. Deliberately narrow: this is a backstop against
catastrophic accidents, not a security boundary, and it does not "understand intent" — extend the
pattern list as real incidents turn up, not preemptively.

### Checkpoint & Rollback (PRD §29)

`host.write_file`/`host.edit_file` write to disk immediately, with no approval gate of their own
— the Permission Engine above only pauses HIGH-risk tools (`host.delete_file`,
`host.run_command`). The other half of "reversible"
is `kirxil checkpoint`/`kirxil undo`, real `git` commits under the hood: if the current directory
is a git repo, every `kirxil run`/interactive goal auto-commits whatever's changed *before* it
starts (silently, and only if there's actually something to commit — a clean tree or a non-repo
folder is a no-op). `kirxil undo` (or `/undo` inside the interactive REPL) resets back to right
before the most recent one of those, after showing the real `git diff --stat` of what it's about
to discard and waiting for a real `y`/`n`. `kirxil checkpoint [message]` is the same snapshot,
triggered manually with your own label instead of automatically before a run.

**Other commands, all real, all achievable in this first pass without a whole Project Brain
(§13 of the PRD, not built):**

- `kirxil run "<goal>"` — one goal, non-interactively, plain-text output (works when
  piped/redirected — scripting-friendly). `--model`, `--dir` to override the defaults.
- `kirxil init` — interactively scaffold a `.kirxil.yml` in the current directory: asks for a
  project name, lets you pick `model.default` from the real `kirxil models` list, and an optional
  `agent.max_iterations`. Asks before overwriting an existing file.
- `kirxil sessions` — lists past agent runs for this workspace, newest first — a real client of
  the same `GET /agents` endpoint the web app's Agents page already uses, just not previously
  reachable from the CLI.
- `kirxil models` — list what this backend currently offers.
- `kirxil git diff` / `status` / `log` / `branch` / `blame <file>` — real `git` (PRD §28: Diff,
  Commits/History, Branches, Blame), run locally wherever you launched this from (not through the
  backend — these are the commands that shell out directly, since they're read-only and
  genuinely local).
- `kirxil search <pattern>` — real `ripgrep`, same way (needs `rg` installed and on `PATH`
  separately — not bundled).
- `kirxil doctor` — checks that a session exists and the backend actually answers, `git`/`rg` are
  really on `PATH` (not just plausible), and whether the current directory is a git repo
  checkpoints can use.
- `kirxil checkpoint [message]` — snapshot the current directory with git (`git add -A &&
  commit`), so `kirxil undo` has somewhere to go back to.
- `kirxil undo` — reset to right before the most recent kirxil checkpoint (`git reset --hard`).
  Shows exactly what will be discarded and asks for a real `y`/`n` first; only ever targets a
  commit kirxil itself made, never an unrelated commit already in the repo's history.

## Tests

### Interactive UI shortcuts

- **Tab** switches the prompt between **CHAT** and **CODE**, preserving your draft.
  The selected mode and model are shown above the input. In CHAT, Enter sends a
  conversation message; in CODE, Enter runs the coding agent with the typed task.
- **/** on an empty prompt opens a two-choice menu: **Auto** and **NVIDIA**.
  Use Up/Down and Enter to select, or Escape to cancel. Slashes within a message
  or path are ordinary text. Use Ctrl+K for the other slash commands.
- NVIDIA selects public, standalone chat, with consent required before every send.
  Choosing it from CODE switches to CHAT. Switching back to CODE selects Auto;
  NVIDIA never receives project context through this mode switch. Mode/model
  changes are blocked while a task or approval is active.

- `/public <question>`: one-shot NVIDIA Nemotron 3 Ultra (free) via OpenRouter.
  Each request asks for confirmation. Use only non-sensitive public information:
  NVIDIA logs usage for security and product improvement. The endpoint sends only
  your question and a fixed system instruction, never project files, conversation
  history, tools, RAG, or personal memories. It does not automatically detect or
  redact secrets you paste. Responses appear locally but are not added to normal
  chat context or saved as server conversations. Aggregate token metrics are recorded.
  No fallback is used and the regular model chain is unchanged. OpenRouter's free
  quota is shared with other free models. No additional NVIDIA API key is needed.

In CHAT mode, plain input uses conversational chat with tool execution disabled. Follow-up
messages reuse the server conversation ID during this CLI session. `/new` starts
a fresh conversation; Ctrl+L only clears the visible transcript. Chat does not make
Git checkpoints. Use `/code <task>` for tool-enabled coding, or `/plan <goal>` to
plan first. Coding runs and chat history are separate contexts; coding does not
automatically inherit chat history, so include the task details in `/code`.

Restart the updated AI service as well as rebuilding the CLI: the backend must
support the new `allow_tools: false` chat request field. Older services may ignore
this field. Chat uses the configured chat provider, not the Hermes agent runtime.

- `Ctrl+K`: open a searchable command palette. Use arrows to select and Enter to
  insert the command into the prompt; selection does not execute it. Escape closes
  the palette and preserves the existing draft.
- `Ctrl+L`: clear finished transcripts while keeping the active run visible.
- `Ctrl+C`: stop an active agent run, reject a pending approval, or exit when idle.
- The banner switches to a compact layout on narrow terminals and after a task
  starts. The footer displays starting/running/planning/verifying/approval states.
- Unknown slash commands show a local error instead of becoming agent tasks.

### Run checks

```powershell
npm test          # vitest, fully offline — fetch is mocked, no running backend needed
npm run typecheck
```

## What this is not (yet)

Against the PRD's own scope: Project Brain (§13) is real now for File Map/Symbol Index/Vector
Index/Semantic Search — see its own section above; Dependency Graph, API Map, Database Map, and
real Git History are still separate, much bigger subsystems, not built. MCP Hub (§16) is real now
for local stdio servers — see its own section above; no remote HTTP/SSE MCP servers yet, and the
deployed container has no Node.js/npx, so npx-based real-world MCP servers can't be configured
against it yet either. No Deployment Engine
(no real deploy target — staging/production environment, cloud account — exists anywhere in this
codebase; building `kirxil deploy` against nothing would be exactly the fabricated-command problem
this project avoids everywhere else), no multi-agent `agent` command (`plan`/`build`/`swarm` are
real — see "Command surface"/"Multi-Agent Swarm" above; no separate `--auto` flag either, since
the CLI's real default behavior already is what §21's Auto Mode describes — see
`docs/architecture/kirxil-cli-prd.md`'s §21 status note), no visual/browser/vision agent, no
plugin ecosystem, no task-type model auto-routing (no real basis to prefer one configured model
over another for a given task — see "Model Router" above; `model.default` is the honest version),
no `monitor`/`project`/`plugin` commands (§33 lists them; they need real infrastructure that
doesn't exist yet, so they're not stubbed in as fake commands either; `memory`, `config`,
`verify`, `swarm`, and `brain` are all real — see above). Self-Healing and Verification (§22) and
Multi-Agent Swarm (§27) are both real now — see their own sections above. Swarm is real parallel
decomposition, not a fabricated Architect/Backend/Security/DevOps roster — every sub-task is the
same one general agent loop, differentiated only by its own real goal text, with no
dependency-aware sequencing between sub-tasks yet. The
Permission Engine is real, with LOW/MEDIUM/HIGH tiers plus a narrow, real BLOCK backstop for
`host.*`/`code.*` run_command tools (see "Permission Engine" above) — nothing is registered at
CRITICAL yet. Checkpoint & Rollback is real but git-based and manual/per-run, not the PRD's
automatic per-*file* undo stack.
All real, separately-scoped future phases — see `docs/architecture/coding-agent.md` for what's
tracked and what isn't yet.
