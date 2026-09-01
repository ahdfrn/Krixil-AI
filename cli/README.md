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

## Log in

```powershell
kirxil login
```

Asks for the api base URL, your workspace slug, email, password, and your real `HOST_ROOT` (see
`services/host-runner/.env`) — saves the session to `~/.krixil/credentials.json`. For
scripted/non-interactive use, set `KRIXIL_TENANT_SLUG`/`KRIXIL_EMAIL`/`KRIXIL_PASSWORD` instead
(same three variables `training/client.py` already reads).

## Use it

```powershell
cd D:\some\real\project
kirxil
```

```
╭ KIRXIL AI ────────────────────────────────╮
│                             ● online       │
╰─────────────────────────────────────────────╯
Project: some-real-project
Branch: main
Model: auto
128 files, 14 folders here
Working in . under D:\. /model to switch, /cwd for folder, /exit to quit.

kirxil > fix the bug where it crashes on empty input

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

┌ ⏸ Bash(pytest -q) ──────────────────────────┐
│ Risk: HIGH                                   │
│ HIGH risk — approve to run it for real, or   │
│ reject to stop this goal.                    │
│ Press y to approve, n to reject.             │
└───────────────────────────────────────────────┘
y

  ⎿ Exit 0
     3 passed in 0.41s

Fixed — the empty-input case now returns early instead of indexing into an empty list.

┌ 1 tool call · +3/-1 ──────────────────────────┐ /help /model /cwd /undo /exit
```

Requires a real terminal (raw-mode stdin, for `Ctrl+C`-to-cancel) — piped/redirected input prints
a clear message and exits rather than crashing. `Ctrl+C` stops a run in progress the same way the
web app's "esc to interrupt" does; `/model [id]` lists or switches models, `/cwd` shows the current
folder, `/plan <goal>` shows a read-only plan in a bordered panel with a real handoff into
`kirxil build`, `/undo` reverts to the last checkpoint, `/exit` quits. A persistent status bar at
the bottom shows the real tool-call count, real test-attempt count (if any), and real
`git diff --stat`-derived change stats for the run in progress.

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
run, including fixing and re-running a genuinely failing test rather than just reporting it.

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
automatic routing *by task type* (Reasoning/Coding/Fast/Vision/Local) is not — this deployment has
exactly two real local models and no benchmark distinguishing which is better at what, so
inventing that mapping would be a fabricated capability, not a real one. Pick your own default
with `model.default` instead.

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

```powershell
npm test          # vitest, fully offline — fetch is mocked, no running backend needed
npm run typecheck
```

## What this is not (yet)

Against the PRD's own scope: no Project Brain (AST/symbol/dependency-graph/vector indexing), no
multi-agent orchestrator (Architect/Debug/Testing/Security/DevOps/etc. as separate coordinated
agents — there's one generic agent loop, same as the web app's, behind every verb below), no
self-healing test-fix-retest loop beyond what the model does on its own within one goal, no swarm
mode, no multi-agent `agent` command (`plan`/`build` are real — see "Command surface" above; no
separate `--auto` flag either, since the CLI's real default behavior already is what §21's Auto
Mode describes — see `docs/architecture/kirxil-cli-prd.md`'s §21 status note), no visual/browser/
vision agent, no plugin ecosystem, no task-type model auto-routing (no real basis to prefer one
configured model over another for a given task — see "Model Router" above; `model.default` is
the honest version), no `deploy`/`monitor`/`project`/`plugin` commands (§33 lists them; they need
real infrastructure — a deploy target, a monitoring stack, a plugin sandbox — that doesn't exist
yet, so they're not stubbed in as fake commands either; `memory` and `config` are both real — see
above). The Permission Engine is real but only LOW/MEDIUM/HIGH are in play for
`host.*`/`code.*` tools today — nothing there is CRITICAL (BLOCK-by-default) yet. Checkpoint &
Rollback is real but git-based and manual/per-run, not the PRD's automatic per-*file* undo stack.
All real, separately-scoped future phases — see `docs/architecture/coding-agent.md` for what's
tracked and what isn't yet.
