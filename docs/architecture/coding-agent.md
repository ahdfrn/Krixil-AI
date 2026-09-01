# Coding agent — file + command access for Agents, sandboxed

## Why this exists

The user asked whether Krixil could code, then asked directly for "kemampuan seperti agen coding
sungguhan (baca/tulis file di proyek nyata, jalankan kode, akses ke codebase Anda)" — a real
coding-agent capability, not a bounded sandbox demo. Confirmed via `AskUserQuestion`: full agent
(read/write real files, run real commands), not a smaller sandboxed-execution-only tool.

This is a different order of risk than everything else in the Tool System. Every prior tool is
either read-only (`knowledge.search`, `web.search`, `usage.get_summary`) or a single narrow
destructive action (`document.delete`). Arbitrary command execution needed a real security design,
not a bolt-on.

## The security design

**A brand-new, separate `sandbox-runner` service (`services/sandbox-runner/`) is the only
component in this stack with Docker socket access — never the `api` container.** Running arbitrary
commands with a real isolation boundary on this stack means Docker-in-Docker, and Docker socket
access is broadly equivalent to root on the host. Rather than accept that risk on the main `api`
container (which handles auth, tool-calling, and everything else), it's isolated to this one small,
single-purpose service. A bug in tool-calling logic, prompt injection, or anything else that makes
`api` misbehave still can't reach Docker or the host — `api` was never given the ability to.
Verified live, not just asserted: `docker exec krixil-api-1 stat /var/run/docker.sock` fails
("No such file or directory"); the same command against `sandbox-runner` succeeds.

This app runs on `localhost` only, single real user, no internet exposure — the realistic blast
radius today is the user's own machine, not a multi-tenant fleet. That's the risk actually being
accepted, and it's why this was surfaced explicitly for sign-off before building rather than buried
in implementation detail.

## Architecture

Four new tools (`app/tools/code_tools.py`), registered into the *existing* Tool System
(`app/tools/base.py`) like everything else — no new agent system, no changes to the Agent loop
(`app/agents/runner.py`) itself, since it already calls `list_tools()` generically:

- `code.list_files`, `code.read_file` — LOW risk, no approval needed.
- `code.write_file`, `code.run_command` — **MEDIUM risk, run immediately, no approval pause.**
  Originally shipped CRITICAL (same approval-gated shape as `document.delete`), matching this
  session's default posture for anything destructive/executable. Changed after the user hit the
  friction directly (approving mid-run interrupts the loop — "Krixil doesn't resume a paused run
  automatically," so a multi-step goal stalls on every write/command) and asked explicitly, after
  being told plainly what it means ("AI bisa langsung eksekusi command... tanpa Anda sempat
  melihat atau membatalkan" — the AI can execute commands immediately, with no chance to review
  or cancel first), to remove the pause for full, uninterrupted agent behavior. This is a real,
  accepted trade-off, not an oversight: nothing now stops between tool calls within a run except
  the existing step/tool-call/time budgets (`agent_max_steps`, `agent_max_tool_calls`,
  `agent_max_execution_seconds`). What still bounds the blast radius is the sandbox itself
  (network-disabled, resource-limited, workspace-confined) and path-traversal protection — not a
  human in the loop. Chat's own tool-calling still only ever offers LOW-risk tools
  (`app/chat/tool_use.py`), so these two remain reachable only through the Agents page, never
  auto-invoked from a plain chat message.

**Path-traversal protection is the load-bearing safety detail** for the file tools
(`app/workspace/fs.py`): `resolve_workspace_path()` resolves the requested path and checks it's
still inside the tenant's own `{workspace_root}/{tenant_id}/` directory before any read/write/list,
rejecting `../` sequences and absolute paths alike (an absolute path silently *replaces* the whole
`Path` on join in Python — `Path("/root") / "/etc/passwd" == Path("/etc/passwd")` — so the check is
on the final resolved path, not on the join going in cleanly). Every tenant gets their own
directory; verified live that tenant A's files are invisible to tenant B.

`code.run_command` calls the new `sandbox-runner` service over the compose network
(`http://sandbox-runner:8001`) rather than executing anything itself. `sandbox-runner`
(`docker-py`) spins up a fresh, auto-removed `python:3.11-slim` container per command with:
- the shared `workspaces` volume mounted, `working_dir` scoped to the tenant's own subdirectory
- `network_mode="none"` — verified live: even DNS resolution fails inside
  (`socket.gaierror: Temporary failure in name resolution`), not just outbound HTTP
- CPU/memory limits (`cpu_quota`, `mem_limit`)
- a hard timeout enforced by `sandbox-runner` itself via `container.wait(timeout=...)`, not just
  trusted to the container's own behavior — a `ReadTimeout` triggers an explicit `container.kill()`

A new "Code" page (`apps/web/src/app/(dashboard)/code/`, `/code` route) lets the user upload,
browse, view, edit, and delete their own workspace files directly — separate from the existing
Agents-page approval flow, matching how `/documents` lets a human directly manage documents outside
the `document.delete` tool. No changes needed to the Agents page itself; it already renders the
generic CRITICAL-tool approval flow.

## A real bug this caught live

**The `workspaces` named volume Compose actually creates is project-prefixed
(`krixil_workspaces`), not the literal string `workspaces` from `docker-compose.yml`.**
`sandbox-runner`'s first version passed `volumes={"workspaces": {...}}` straight to
`docker_client.containers.run()` — Docker silently created and mounted a *brand new, empty* volume
literally named `workspaces` instead of the real shared one, since the string didn't match any
existing volume. First live test caught it immediately: a file written via `code.write_file`
through the `api` container was invisible when `code.run_command` tried to read it back
(`No such file or directory`), even though `code.list_files` on `api` showed it existed fine.

Fixed by not hardcoding the volume name at all: `sandbox-runner` asks the Docker API what volume is
actually mounted at `/workspaces` on *its own* container (`docker_client.containers.get(hostname)`,
then reading `Mounts[].Name` for the `/workspaces` destination), resolved once and cached. This is
correct regardless of the Compose project name, rather than depending on the `name: krixil` in
`docker-compose.yml` staying what it is today.

## A second real bug — approving a paused Agent step never updated the run itself

Found live during a demo, not in review. Approving a `pending_approval` execution (via
`POST /tools/executions/{id}/approve`, the same generic endpoint every CRITICAL tool uses) really
did run the tool — but the *Agent run* that had paused on it stayed frozen at
`status: "waiting_approval"` forever, with its last step still showing
`{"status": "pending_approval", ...}`, because nothing had ever gone back and updated the
`AgentRun`/`AgentStep` rows once approval happened outside the run loop (`run_agent()` had already
returned its HTTP response and wasn't running anymore). The Agents page dialog kept showing
"Waiting on your approval" indefinitely with no way to see the real result — a genuinely broken
feedback loop, not just a display lag.

Fixed with `_resolve_paused_agent_run()` (`app/tools/service.py`), called from both
`approve_execution()` and `reject_execution()`: finds the `AgentRun` with
`pending_execution_id == execution.id`, rewrites its last (previously `pending_approval`)
`AgentStep` with the real outcome, and sets the run's own `status` to `completed` / `stopped`
(rejected) / `failed`. The frontend (`apps/web/.../agents/page.tsx`) also had to actually refetch
the run after approving/rejecting — it was applying the same "one-shot snapshot from when the
dialog opened" pattern that would have hidden the fix either way.

## Approval removed for `code.write_file` / `code.run_command`

Originally both were CRITICAL risk, approval-gated like `document.delete` — the default,
conservative posture for anything destructive or executable. In practice this collided with what
the user actually wanted: a multi-step goal ("read this, fix that, run the tests") stalls on
*every single* write or command, since `run_agent()`'s loop doesn't resume automatically after a
pause. After hitting this friction directly and being told plainly what removing the approval
step means — the AI can execute commands immediately, with no chance to review or cancel first —
the user asked for it anyway, explicitly, in order to get uninterrupted, "professional coding
agent"-style behavior. Changed to MEDIUM risk (see `app/tools/code_tools.py`): now bounded only by
the sandbox's own containment (network-disabled, resource-limited, workspace-confined),
path-traversal protection, and the run's existing step/tool-call/time budgets — not by a human in
the loop. This is a deliberate, informed trade-off specific to this single-user, `localhost`-only
deployment, not a default to carry forward blindly into a more exposed one.

## Verification

All live, against the real running stack (not simulated): registered account, real Docker daemon,
real containers.

- `code.write_file` → `code.read_file` returns the exact content just written (originally verified
  through the approval flow, before it was removed — see above).
- `code.read_file`/`code.write_file` with `../../etc/passwd` → rejected with a clear error, tool
  status `failed` (not a 500 — validated as a normal, expected input rejection).
- `code.run_command` (`python verify/hello.py`) → after the volume-name fix, genuinely reads the
  file `code.write_file` wrote — proof the shared workspace actually works end-to-end across both
  containers, not just within one.
- Network isolation: a command attempting `urllib.request.urlopen("https://example.com")` inside
  the sandbox fails at DNS resolution, not just at the HTTP layer.
- Docker socket: present in `sandbox-runner`, absent in `api` — checked directly via `docker exec`
  against both containers.
- Real Agents-page run against genuine Ollama tool-calling: goal "run `python hello.py`", the model
  correctly planned and called `code.run_command`; after the approval-reconciliation fix, the
  dialog correctly showed the real `stdout`/`exit_code` once run.
- Frontend: full Playwright pass against the live app (real login, not mocked) — upload a file, see
  it listed, open and edit it, save, reload the page and confirm the edit persisted, delete it, back
  to the empty state. Zero console errors.
- Backend: 141/141 tests pass (`test_workspace_fs.py`, `test_code_tools.py`,
  `test_workspace_router.py`, `test_tools.py`'s registered-tool-names assertion, and
  `test_agents.py`'s new approval-reconciliation coverage), ruff clean, mypy clean, frontend
  `tsc --noEmit` clean.

## Real host-folder access — a second, separate trust model

Everything above stays confined to an isolated, per-tenant workspace. The user then asked directly
for the real thing: pick any folder under `D:\` and have the AI read/write/run there **on this
actual Windows machine** — "seperti agen coding sungguhan" again, but this time meaning genuinely
unsandboxed, not the isolated demo. Confirmed explicitly via `AskUserQuestion`, with the trade-off
stated plainly first: whole `D:\` as the root, and no Docker sandbox for command execution — real
`subprocess` calls with full network access, using whatever's actually installed (the user's own
Python, git, node, PATH), not a container's limited toolchain.

**Say this plainly, because it's the whole risk of this feature**: this gives the AI real,
unsandboxed read/write/execute access to everything under `D:\` — including this project's own
source (`D:\Krixil`) — with no approval step and full internet access, driven by a local LLM that
makes mistakes. There is no sandbox left to catch a bad command; it runs for real, exactly as if
typed by hand. The only remaining guardrail is confinement to `D:\` itself.

**New: `services/host-runner/`** — a small, separate native-Windows FastAPI app (own venv, styled
after `training/`'s existing setup, *not* in Docker), binding to `127.0.0.1` only. Reached from the
`api` container the same way the natively-installed Ollama already is
(`http://host.docker.internal:8002`) — verified live that Docker Desktop for Windows really does
let a container reach a host service bound to `127.0.0.1` this way (the same mechanism that's been
making the Ollama integration work all along). `app/fs.py` mirrors
`app/workspace/fs.py`'s `resolve_workspace_path()` pattern for Windows absolute paths under
`HOST_ROOT` — the one safety rail this service keeps. `POST /run` is a direct
`subprocess.run(..., shell=True, cwd=directory, ...)`, no isolation.

**Four new tools** (`app/tools/host_tools.py`): `host.list_files`/`host.read_file` (LOW risk),
`host.write_file`/`host.run_command` (MEDIUM risk, no approval — consistent with the choice
already made for the sandboxed `code.*` tools, extended here even though there's no sandbox left
underneath it). All are thin HTTP proxies to `host-runner`. A parallel `/host/files` router
(`app/workspace/host_router.py`) serves the same role `/workspace/files` does for direct,
human-driven browsing — bypassing the Tool System, translating a `host-runner`-unreachable
`ConnectError` into a clear `503` rather than a generic failure.

**Frontend**: the Code page gained a root switcher — **Workspace** (existing, isolated, default)
vs **This Computer (D:\)** — with a persistent red warning banner while the latter is active.
Picking any real subfolder under `D:\` (including `D:\Krixil` itself) through the ordinary
click-to-navigate file browser *is* "choose the directory you want" — Docker's static-mount model
is what forces the root itself (`D:\`) to be fixed at `host-runner` startup rather than picked
per-request, but everything within that root is fully dynamic through the UI already built.
`buildCodeGoal()` (`apps/web/.../code/page.tsx`) now names the tool family explicitly
(`code.*` vs `host.*`) in the framed goal, since both are registered simultaneously and the model
needs to be told which one a given goal means.

Verified live end-to-end, using a disposable test folder (never `D:\Krixil` itself): real file
write and read via the tools, path confinement rejecting `C:/Windows/win.ini` with the real
`host-runner` error message (not a generic "400 Bad Request" — `httpx.HTTPStatusError.__str__`
doesn't include the response body, so this needed an explicit re-raise as `ValueError` with the
extracted `detail`, same pattern `app/workspace/host_router.py` uses for the human-facing side),
and a real `host.run_command` producing genuine `stdout` from a file the AI itself had just
written — confirmed against the actual Windows filesystem outside the app entirely (`Get-ChildItem
D:\...`), not just the app's own view of it. All existing backend tests still pass (150/150) with
the new `test_host_tools.py`/`test_host_router.py` added; ruff and mypy clean.

## Stronger coding skills — git, testing, error handling

The user asked to strengthen the coding agent itself rather than keep chasing a bigger base model
(a genuine hardware ceiling — see below). Turned out to need almost no new code: `code.run_command`
already executes arbitrary shell commands, so git and running a test suite were already possible in
principle — the sandboxed Workspace container just didn't have `git`/`pytest`/a compiler installed
(`services/sandbox-runner/app/main.py`'s `RUNNER_IMAGE` was bare `python:3.11-slim`), and the system
prompt never told the model to actually use them well.

Fixed with a purpose-built image (`services/sandbox-runner/runner-image/Dockerfile`: `git`,
`build-essential`, `pytest`, plus a pre-set git identity — commits would otherwise fail outright on
a fresh container with no `user.email`/`user.name` configured, an easy miss caught before it ever
shipped) built as `krixil-sandbox-python:latest` and referenced by `RUNNER_IMAGE`. "This Computer"
mode needed no changes — it already uses whatever's on the real machine, git included, already
verified live in an earlier session. `app/agents/prompts.py`'s `SYSTEM_PROMPT` gained three lines:
use git with real commit messages when it fits, read the actual error before deciding what to do
next, and keep iterating on failing tests rather than stopping after one attempt.

Verified live: `git --version`/`pytest --version`/`gcc --version` all present in a fresh sandbox
container; a genuine `git init && add && commit && log` sequence worked end-to-end with a real
commit hash. Also caught and fixed, along the way: `code.run_command`/`host.run_command`'s
`timeout_seconds` field had a tight upper bound (120s/300s) that hard-*rejected* a longer request
outright — the model kept asking for 300s and got a validation error instead of the graceful
`min()` clamp against `code_execution_timeout_seconds`/`host_runner_timeout_seconds` that was
already sitting right there in the handler, just never reached. Widened both bounds to 600s so the
existing clamp is what actually enforces the ceiling.

**A genuine, honest limit found live, not fixed by this change**: goals requiring several
tool calls in sequence (e.g. "run the tests, read the failure, fix the bug, run the tests again")
made `llama3.1:8b` *narrate* a full plan — including fabricated tool outputs it never actually
received — instead of calling tools one at a time, consistently (3/3 attempts, both conditional and
plain numbered-step phrasing). A single-step goal with the same prompt worked fine every time,
isolating this to multi-step sequencing specifically, not the prompt change or a phrasing choice.
This is a real capability ceiling of a small local model doing extended agentic tool orchestration,
not something prompt engineering alone resolves — the practical takeaway for now is that this model
is reliable for single, well-scoped steps and unreliable for long conditional chains in one goal.

## Live, step-by-step transcript — closes the "results only appear after the whole run finishes" gap

User asked to make the Code page look and behave as close to Claude Code as reasonably possible.
Two separate changes, backend then frontend, in that order since the frontend redesign only
matters once there's something to show progressively.

**Backend: `POST /agents/run` no longer blocks for the whole loop.** It used to run
`run_agent()` synchronously inside the request — up to `agent_max_execution_seconds` (120s) with
nothing visible until the very end, and every `AgentStep` was only `flush()`'d (visible within
that one request's own open transaction), not `commit()`'d, so even a client polling
`GET /agents/{id}/status` from a separate connection couldn't have seen partial progress if it
tried. Now: `create_agent_run` still runs inline (fast, just an insert) and the endpoint commits
and returns immediately with `status: "running"`; the actual loop runs via `BackgroundTasks` in a
new function, `_run_agent_in_background` (`app/agents/router.py`) — its own `AsyncSessionLocal()`
session, a `TenantContext` rebuilt from plain values (never an ORM object or the request's session
crossing the background-task boundary, the same lesson `app/memory/long_term.py` already
established twice). `_record_step` (`app/agents/runner.py`) now does a real `commit()` per step,
not a `flush()`, so each step becomes visible to any other connection — specifically a client
polling status — the instant it happens, not just at the end. The memory-extraction call that used
to be scheduled from the router now happens directly inside this same background function, awaited
normally, since it's already off the request's critical path.

**Frontend: `pollAgentRun` (`lib/api/agents.ts`)** — fetches `GET /agents/{id}/status` on an
interval (default 1.2s), calling back with each result, until the run leaves `"running"`. Both
the Code page and the Agents page push a run into their local state the instant `runAgent()`
returns (status `"running"`, no steps yet) and let this poll fill it in live, rather than waiting
for a single final result the way both pages used to.

**A real race this exposed, caught only by driving the actual browser, not by lint/tsc**: the Code
page's session-history-restore effect (`useEffect` on `[root, dir]`) fetches this session's past
runs on mount/session-switch and used to `setRuns(details)` — a plain overwrite. That was safe
before, because a freshly-submitted goal used to take seconds-to-minutes to land in `runs`, long
after that fetch had resolved. Now that `runAgent()` returns in milliseconds, submitting a goal
right after the page loads can beat that fetch to the finish line — its later-arriving
`setRuns(details)` was silently wiping the just-added running turn back out of view (the run itself
kept executing server-side the whole time; only the UI lost track of it, confirmed by querying
`GET /agents` directly and finding it `completed` with nothing shown on screen). Fixed by tracking
staleness (skip applying a response for a `(root, dir)` the user has already navigated away from)
and merging instead of overwriting (`prev` entries not present in the freshly-fetched list survive
the merge, since they were added locally after the fetch started).

**Frontend: `StepView` (`components/agent-run/step-view.tsx`) redesigned** — a compact, monospace,
single-line-per-tool-call shape (`Bash(cmd)`, `Write(path)`, `Read(path)`, ...) with a thin colored
left rail instead of a bordered card, matching Claude Code's own terminal-flavored tool feed more
than the previous chat-bubble-style cards. Long results (a big directory listing, file content, or
command output — more than 8 lines) collapse behind a click-to-expand toggle by default; short
ones just show. A new `WorkingIndicator` (pulsing dot + step count) renders under a run's steps
while `status === "running"`, replacing the old static "this can take up to two minutes" copy that
made sense for a blocking request and doesn't for a live-updating one.

**What this does NOT change**: an individual `code.run_command`/`host.run_command` call still only
returns its stdout/stderr once that one command finishes — there's no byte-level streaming of a
single long-running command's output. What's live now is the run's *step-by-step* progress (each
completed tool call/observation appearing as it happens), not intra-command streaming. Still
deliberately out of scope, same reasoning as before.

Verified live: a real goal against the actual Ollama-backed model, confirming `POST /agents/run`
returns in ~10ms and `GET /agents/{id}/status`, polled every 1.5s, shows `steps_len` growing from 0
to its final count across several polls rather than jumping straight to the end — the loop was
genuinely running in the background the whole time. Also drove the real browser (Playwright):
submitted a goal, confirmed the new turn renders immediately and its result grows step by step, and
specifically re-tested the race above after the fix to confirm it survives a goal submitted
immediately on page load. `pytest` 151/151 (`tests/test_agents.py` rewritten to assert against a
follow-up `GET .../status` call instead of the `POST /agents/run` response body directly, since
that response is now just the just-created "running" row, not the finished result — background
tasks still run to completion before `client.post(...)` returns in tests, so no sleep/retry was
needed), ruff/mypy/tsc/eslint all clean.

### Round two — a genuinely terminal-flavored transcript, and a real "esc to interrupt"

User's first look at the above wasn't convinced — the tool-call rendering had changed but the page
around it (chat bubbles, rounded cards, a labeled form) still read as a generic dashboard, not
Claude Code. Two more changes, asked for explicitly as "as close as possible, including function."

**`StepView` rewritten again**, this time dropping every bordered "card"/icon-set choice in favor
of literally the same two glyphs Claude Code's own transcript uses: `⏺ Tool(args)` for a tool call,
and an indented `⎿ summary` underneath for its result — plain monospace text, a colored bullet/
summary (green success, red error, gray neutral), no backgrounds, no per-tool icon set. The run's
own goal line dropped the primary-colored chat bubble for a plain `› instruction` prompt line, and
the composer became an actual prompt: a `›` marker, borderless auto-growing textarea, Enter-to-run/
Shift+Enter-for-newline, no visible label.

**A real "esc to interrupt"**, closing a small but real functional gap: previously nothing could
stop a run once started; Claude Code lets you interrupt with Escape. `POST /agents/{id}/cancel`
(`app/agents/router.py`) flips a still-`"running"` row's status to `"cancelled"` directly (a no-op
if the run already finished naturally — a race against the loop's own completion, not an error to
surface) and does nothing else — no direct task-kill. `run_agent`'s loop (`app/agents/runner.py`)
notices on its own: every iteration now `session.refresh(agent_run, attribute_names=["status"])`
before the (potentially several-second) model call, checking for `"cancelled"` and returning
immediately if so — expire_on_commit=False means the loop's own in-memory row otherwise never sees
a status change made by a different session/connection, the same reason `_record_step` needed a
real `commit()` in round one. This means cancelling still takes effect *between* steps, not
mid-model-call — the same "finishes the current thing, then stops" shape Claude Code's own
interrupt has, not instant. Frontend: `WorkingIndicator` grew a ticking elapsed-seconds counter
(`useElapsedSeconds` — reads `Date.now()` inside a `setInterval` effect, not inline during render,
since React's purity rule correctly rejects an impure clock read during render) and an "esc to
interrupt" button calling the new `cancelAgentRun()`.

Verified live: submitted a real goal, waited for the working indicator with its live elapsed timer
and stop button to appear, clicked it, and confirmed via a direct API call — not just that the
button disappeared — that the run's status genuinely reached `"cancelled"` with a `step_count` of 0
(caught before its very first tool call). Also re-screenshotted a session with older, genuinely
real (non-hallucinated) tool-call history under the new styling to confirm the `⏺`/`⎿` rendering
holds up outside a freshly-generated run, not just a cherry-picked happy path. New backend tests:
cancelling before the loop's first iteration stops it with zero steps recorded and no model call
made (a real HTTP-level race — cancelling a run genuinely mid-execution — isn't reproducible
deterministically against `MockProvider`'s instant responses in the offline suite, so this proves
the check itself works at the earliest point it can fire, not a full mid-run race), the cancel
endpoint is a no-op against an already-finished run, and it's tenant-scoped like every other agent
endpoint. `pytest` 154/154 (+3), ruff/mypy/tsc/eslint all clean.

### Round three — dropping the sandboxed "Workspace" mode, a real model selector, real attachments

Even the terminal-flavored transcript from round two wasn't judged close enough — the page itself
still had chrome (a root-mode toggle, a bordered file browser) the reference product doesn't. User
confirmed, explicitly and after being told the real consequence, that the sandboxed `code.*` path
should come out of the Code page's UI entirely: **every new goal from this page now targets
`host.*` only** — real, unsandboxed access, no safer default left to switch to here. `code.*` and
`services/sandbox-runner` themselves are untouched (still registered, still reachable if something
else calls them directly); only this page stopped offering the choice. The Workspace-exclusive
file browser/upload/edit-file feature necessarily went with it (it never existed for `host.*`
mode, by the same "goal-driven only" decision recorded earlier in this doc) — re-added afterward
in a narrower, real shape: an attach-files button that uploads straight into the open folder via
the same `host.write_file` endpoint the removed browser used, then tells the model to read it.
`apps/web/src/stores/code-sessions-store.ts` now filters the sidebar to `host` sessions only, since
an old `workspace`-rooted session link is no longer navigable from this page (the runs themselves
are untouched in the database — just not reachable through this particular UI anymore).

Two more real, not decorative, additions landed in the same pass, both because a fake version
would have violated this project's own "no placeholder controls" rule outright:

- **A real per-run model selector.** `AgentRunRequest` gained an optional `model` field, threaded
  through `_run_agent_in_background` into `run_agent(..., model_id=...)`, which forwards it as a
  `model=` kwarg on every `tool_call` the run makes — the exact mechanism Chat's own per-message
  model switching already used for Ollama's multiple local tags (`CloudModelProvider` merges
  `**kwargs` into its request payload). Reuses the existing, real `ModelSelector` component
  (`components/chat/model-selector.tsx`) rather than a new one. Live-verified by explicitly
  requesting `qwen2.5:7b` for a real run and getting back "I am Qwen, developed by Alibaba Cloud"
  as the final answer — proof the selection genuinely reaches the model, not just the UI.
- **A real attach-files button**, in a dropdown matching the reference's "+" menu shape exactly
  (`Add files or photos`, `Slash commands`, `Connectors`, `Add plugins`) — but only the first item
  is enabled. The other three have no system behind them anywhere in Krixil (no command registry,
  no OAuth/connector framework, no plugin loader), so they're shown visibly disabled rather than
  wired to nothing; a menu item that looks clickable but silently does nothing is worse than one
  that's honestly grayed out. "Add files or photos" opens a native file picker, uploads the
  selection into the currently-open folder, shows it as a chip (reusing
  `components/chat/file-attachment-chip.tsx`), and mentions the attached filename(s) in the goal
  text sent to the model. Verified live end to end including the failure path: with `host-runner`
  stopped, a real upload attempt correctly showed "Upload failed" (not a fake success); with it
  running, the file genuinely landed on disk (confirmed by reading it back, then deleted as a
  throwaway test artifact) and the chip correctly flipped to "Ready".

`pytest` 156/156, ruff/mypy/tsc/eslint all clean.

## A second client: `cli/`, a terminal coding agent (Python version, superseded — see below)

> This section describes the CLI's original Python implementation. It was rebuilt in Node.js/
> TypeScript shortly after (next section) once the user supplied a formal PRD for it specifying
> that stack; the Python version still exists at `cli-python/` for reference and its design
> reasoning below still applies to the rewrite (same backend contract, same goals), but isn't
> the current implementation.

User asked for "a powerful CLI like Blackbox and others." Deliberately **not** a second
implementation of the agent loop — `cli/` is a plain Python client (real `pip install -e .` /
`krixil` command, via `[project.scripts]`) of the exact same `POST /agents/run`/
`GET /agents/{id}/status`/`POST /agents/{id}/cancel` the web Code page already uses, so every
backend guarantee documented above (live step-by-step commits, cancellation between steps, real
model selection) already applies to it for free. `cli/krixil_cli/render.py` is a direct,
line-by-line port of `step-view.tsx`'s summarization/rendering logic to `rich` renderables, so the
terminal transcript reads identically to the web one — same `⏺ Tool(args)` / `⎿ result` shape,
same tool-name-based summaries.

**Session**: `krixil login` prompts for the api base URL, workspace slug, email, password, and the
real `HOST_ROOT` this machine's `host-runner` is configured with (asked once, not queryable from
the client), then saves a session to `~/.krixil/credentials.json`. Falls back to
`KRIXIL_TENANT_SLUG`/`KRIXIL_EMAIL`/`KRIXIL_PASSWORD` env vars (the same three `training/client.py`
already reads) for non-interactive use with no `login` step.

**"Operates where you're standing"**: `krixil` (no args) computes the goal's `dir` from
`Path.cwd()` expressed relative to the configured `HOST_ROOT`, falling back to the root folder if
launched entirely outside that tree (since `host.*` tools can't reach there regardless of what the
CLI computes) — the same real-terminal-agent feel Claude Code itself has, without needing any
server-side change to how `HOST_ROOT` confinement works.

**Live rendering**: `rich.live.Live`, redrawn on each `GET /agents/{id}/status` poll (1s interval),
mirrors `pollAgentRun`'s role on the web exactly. `Ctrl+C` calls the same `POST
/agents/{id}/cancel` the web's "esc to interrupt" button does, then fetches one more time so the
transcript reflects the real final state rather than freezing mid-render.

**Verified live**, from a real folder on the user's own machine, not just offline tests: a genuine
`host.list_files` call against an empty real folder rendered correctly end to end; a real
write-then-read file round trip (confirmed the file actually existed on disk, then cleaned it up);
explicit `--model qwen2.5:7b` selection changing which model actually answered, the same live
check done for the web's selector. And, unprompted — the CLI reproduced the exact same
`llama3.1:8b` narrate-instead-of-call limitation documented in "Stronger coding skills" above on a
two-step goal (write a file, then run it), which is the right outcome: the CLI is a faithful
client of the real backend, not a differently-behaved reimplementation, so a real model limitation
shows up identically in both places rather than being hidden by different plumbing.

20 offline tests (`pytest-httpx` mocks every HTTP call — no running backend needed to test the
CLI's own logic: goal-building, `dir` computation, session persistence, rendering), ruff/mypy
clean. See `cli/README.md` for setup and usage.

## `cli/` rebuilt in Node.js/TypeScript against a formal PRD

User supplied `KIRXIL_AI_CLI_PRD_v1.0.pdf` — a full "Autonomous Software Engineering Platform"
product vision (multi-agent orchestrator, Project Brain with AST/vector indexing, self-healing
test loop, visual/browser/vision agents, a 15+ service plugin ecosystem, swarm mode, all the way
to V1.0) — and asked to "update the CLI" with it. Given the real size of that document (reproduced
in full at [`kirxil-cli-prd.md`](kirxil-cli-prd.md)), the response wasn't to build all of it: it's
explicitly a multi-year roadmap, and most of it (Project Brain, multi-agent orchestration,
self-healing, browser/vision agents, the plugin ecosystem) has no foundation anywhere in Krixil
yet and would take actual weeks, not one session — said so plainly before starting, and the user
confirmed anyway to proceed with what was realistic: the PRD's **own** recommended build order
(§50: "01 CLI Runtime" first) and MVP scope (§37), scoped specifically to a stack decision, not
the whole platform.

**The one part of the PRD followed literally**: its suggested CLI stack — TypeScript, Node.js,
Ink, Commander, Zod, execa — replacing the working Python CLI (moved aside to `cli-python/` for
reference, not deleted, since nothing about this session's work had been committed to git yet and
discarding real working code without a recovery point would have been reckless). **The one part
of the PRD deliberately NOT followed**: its suggested *backend* stack (TypeScript/Fastify/
Postgres/Redis/BullMQ) and its suggested monorepo restructuring (`apps/`+`packages/` layout) —
`services/ai-service` stays Python/FastAPI (already built, already tested, 156 passing tests;
rewriting it would discard that for no functional gain), and the repo keeps its existing
`services/`/`apps/web/`/`cli/` layout rather than being restructured wholesale. Both deviations
are called out explicitly in `kirxil-cli-prd.md` itself, not silently decided.

**Architecture, same contract as the Python version, new runtime**: `cli/src/api.ts` (native
`fetch`, `zod`-validated responses — same endpoints, same shapes as `krixil_cli/api.py`),
`cli/src/goal.ts` (`buildGoal`/`dirFromCwd`, same logic), `cli/src/render.ts` (framework-free
step-summarization logic — `⏺ Tool(args)` / `⎿ result`, matching `step-view.tsx`/`render.py`
exactly), consumed by **two** renderers so scripted/piped use isn't held hostage to a real
terminal: `cli/src/ui/*.tsx` (Ink/React components — `App`, `Banner`, `Transcript` — for the
interactive REPL) and `cli/src/runOnce.ts` (plain `console.log`, for `kirxil run "<goal>"`, which
needs to work when piped/redirected — Ink's raw-mode terminal takeover assumes a real TTY and
can't be used for that). `kirxil login`/`logout`/`models`/`run`/the default interactive command
all work the same way the Python version's did. Two small, real, PRD-MVP-aligned additions the
Python version didn't have: `kirxil git diff`/`kirxil git status` and `kirxil search <pattern>`
(real `ripgrep`) — both shell out via `execa` directly on the machine the CLI runs on (not through
the backend), since they're read-only and genuinely local; ripgrep itself isn't bundled, has to be
installed separately.

**Three real bugs found live, none of them from the offline test suite** — the same pattern this
whole project's history has, now caught by a *second* client hitting the same backend from a
different angle:

1. **A genuine backend ordering bug**: `list_agent_steps` (`app/agents/service.py`) ordered only
   by `step_number` — but a tool_call and its own observation share one loop iteration's
   step_number by design, and Postgres has no obligation to return same-`step_number` rows in
   insertion order without a secondary sort key. Caught when the CLI printed `⎿ No files here`
   *before* `⏺ List(demo)` for a real run — confirmed by querying `GET /agents/{id}/status`
   directly, proving the API itself returned them swapped, not a client rendering bug. This means
   the **web app had the exact same latent bug** the whole time, just never happened to hit the
   unlucky ordering live. Fixed with a real secondary sort key, `AgentStep.created_at` (already
   µs-resolution and Python-side per `TimestampMixin`, and reliably sequential now that round
   two's per-step commits mean tool_call and observation are genuinely separate transactions, not
   tied at the same timestamp). New regression test asserts the literal step *sequence*
   (`["tool_call", "observation", "final_response"]`), not just that both types are present
   somewhere in the list, which is what the existing test had actually been checking.
2. **A real cross-drive path bug in `dirFromCwd`**: Node's `path.relative()` between two different
   Windows drives (e.g. `HOST_ROOT` on `D:\`, launched from `E:\`) can't express a true relative
   path, so it returns the target path back essentially unchanged — which does *not* start with
   `".."` the way an ordinary "outside the tree" case does, so the existing `startsWith("..")`
   check missed it entirely. Caught by a unit test, not manual poking — `path.isAbsolute()` on the
   result catches this case too.
3. **A real error-handling bug in `kirxil search`**: `execa(..., { reject: false })` means a
   *spawn* failure (the `rg` binary genuinely missing) doesn't throw either — it comes back as
   `.failed` with empty stdout, indistinguishable from "ripgrep ran and found nothing" unless
   checked explicitly. Caught live: on this machine, what looked like an installed `rg` (`rg
   --version` worked in one shell) turned out to be a shell function belonging to unrelated local
   tooling, not a real, independently-resolvable `ripgrep` binary at all — genuinely absent from
   both PowerShell's and a plain child-process spawn's PATH. The bug silently printed "No
   matches." instead of the true "ripgrep isn't installed" state. Fixed by checking `.failed`
   explicitly; real ripgrep was then installed via `winget` and the corrected command re-verified
   against it for real, both the "missing" and the "found matches" paths.

Also fixed, less dramatic but real: the interactive REPL crashed with a raw React error-boundary
stack trace when launched with piped/non-TTY stdin (Ink's `useInput` needs raw-mode-capable
input), instead of pointing at `kirxil run` — now checked upfront with a clear message.

Verified live end to end again post-rewrite, same rigor as the Python version: `kirxil run` from a
real folder showing the correct `⏺`/`⎿` order after the backend fix, `git status`/`git diff`
against this repo's own real (uncommitted at the time) changes, the interactive REPL's banner
(`Project:`/`Branch:`/`Model:` — `Branch` read directly from `.git/HEAD`, honestly showing `—`
rather than a fabricated name outside a git repo) rendering correctly in a real terminal.
22 offline tests (`vitest`, `fetch` mocked — no running backend needed), `npm audit`: 0
vulnerabilities (an initial `vitest@2.1.8` pin pulled in a vulnerable `esbuild`/`vite` chain via
its own dev dependencies — a dev-only, not-shipped issue, but bumped to a clean major version
anyway rather than left as a real-looking audit warning), tsc clean. See `cli/README.md`.

## Permission Engine wired end-to-end for the CLI (PRD §17)

Follow-up pass, same session as the rewrite above: the PRD's Permission Engine (LOW/MEDIUM/HIGH/
CRITICAL → AUTO/ASK/BLOCK) already existed in the backend — `app/tools/base.py`'s `RiskLevel`,
`app/tools/service.py`'s pause-on-`pending_approval` flow, `POST /tools/executions/{id}/approve|
reject` — and was already used by the web app's Agents/Tools pages for tools like
`document.delete` (CRITICAL). It was real, just never actually reachable through `host.*`: both
`host.write_file` and `host.run_command` topped out at MEDIUM, and `APPROVAL_REQUIRED_LEVELS` only
gates HIGH/CRITICAL — so nothing the CLI ever called could pause. Bumped `host.run_command` to
HIGH (arbitrary shell execution is the PRD's own example of a HIGH-risk action, and a strictly
bigger blast radius than `host.write_file`'s single-file MEDIUM, left unchanged) — now a real
`kirxil` run pauses, prints the exact command and its risk level, and blocks on a genuine `y`/`n`
(`cli/src/runOnce.ts` for `kirxil run`; a bordered Ink prompt in `cli/src/ui/App.tsx` for the
interactive REPL) before `host-runner` ever sees it.

**The bigger fix underneath it**: `run_agent()` (`app/agents/runner.py`) previously had no way to
resume after a pause — `approve_execution` ran the approved tool and then terminated the run
outright, handing back that one result. This is the exact limitation called out above in
"Approval removed for `code.write_file`/`code.run_command`" as the reason approval was pulled from
those tools entirely (a multi-step goal "stalls on *every single* write or command"). Fixed
properly instead of worked around: `run_agent` now takes a `resume` flag that rebuilds the message
history from the run's persisted `AgentStep` rows (`_rebuild_messages`) and continues the loop
from the next step number; `AgentRun.model_id` is now persisted (new column, migration
`0012_agent_run_model_id`) so a resumed run keeps using the model it started on, since the
background task that resumes it (scheduled from `POST .../approve`, not the original request) has
no access to the original request payload. Approving a paused `host.run_command` now genuinely
lets the agent keep working — it isn't stuck choosing between "no approval at all" and "approval
that kills the run" anymore. This doesn't retroactively change the earlier `code.*` decision (that
was the user's own explicit, informed call, for the sandboxed Workspace path specifically, and
still stands) — but the specific technical reason given for it no longer fully applies, worth
knowing if that trade-off gets revisited.

Verified live against the real running stack, not just the offline suite: real Ollama model,
real `host-runner`, a genuine `kirxil run` goal that called `host.run_command`, paused, and
printed the HIGH-risk prompt; approved with a real `y` — the run resumed, the real model produced
a second, coherent response reasoning about the command's actual output; rejected with a real `n`
on a second attempt — cleanly stopped, `host-runner` never invoked (confirmed via `respx`'s
call-count assertions in the equivalent backend tests, and by the CLI transcript itself showing no
result for the rejected command). Also caught and fixed live: `buildGoal` (`cli/src/goal.ts`) told
the model to prefix commands with `` `cd ${dir} &&` `` even though `host.run_command` already has
its own `directory` argument for exactly that — the model sometimes did both, producing a
double-applied path that failed with a real "not found" error; instruction reworded to say to use
the `directory` argument instead and not `cd` from within the command string too. Backend: 158/158
tests pass (up from 157; new/updated coverage in `test_agents.py`, `test_host_tools.py`), ruff and
mypy clean. CLI: 27/27 tests pass (up from 22), `tsc --noEmit` clean.

## Checkpoint & Rollback for the CLI (PRD §29), and a real Windows bug in `kirxil search`

Same session, continuing straight through the PRD. `host.write_file`/`host.run_command` write to
disk immediately with no gate of their own beyond the Permission Engine above — the other real
safety net a PRD-aligned CLI needs is being able to get back out of a bad run, per the PRD's own
philosophy line (§48: "Kesalahan harus dapat dipulihkan — Checkpoint first"). Built as real `git`
commits (`cli/src/checkpoint.ts`), not a custom undo log: `kirxil run`/the interactive REPL
auto-commit whatever's already changed in the current directory right before a goal starts
(silent no-op outside a git repo, or when the tree's already clean — no empty commits piling up
across a session); `kirxil undo` (`/undo` inside the REPL) resets to right before the most recent
one of those, after printing the real `git diff --stat` of what it's about to discard and waiting
for an actual `y`/`n` — the same confirm pattern the Permission Engine prompt uses, generalized
in `cli/src/ui/App.tsx` into one `waitForConfirm` both now share. `kirxil checkpoint [message]` is
the same snapshot on demand, with your own label. Deliberately scoped to git — no Krixil-native
journal, nothing outside a git repo, and `undo` only ever targets a commit kirxil itself made
(matched by its own commit-message prefix), never arbitrary history already in the repo.

**A second, real, unrelated bug found while building this**: `kirxil search`'s existing
"is `rg` actually installed?" check (added earlier this session, see above) turned out not to
actually work on Windows. Investigated because `checkpoint.ts` needed the same kind of "did this
git command actually find something" check, via execa's `.failed`/`exitCode` — and testing that
in isolation showed `execa`/`cross-spawn` resolves an unresolvable binary through `cmd.exe` on
Windows, which prints `'rg' is not recognized...` to stderr and exits 1 — the *identical*
`.failed`+`exitCode` shape as ripgrep's own documented "ran fine, zero matches" exit code, with no
`ENOENT` or other distinguishing field surfacing through execa's result object either way (checked
directly). So the existing `if (result.failed)` check on the search itself was reporting "isn't
installed" on every genuine zero-match search too, not only when `rg` was actually missing — the
earlier fix addressed the *symptom* (a missing binary silently looking like "no matches") but
introduced the exact same ambiguity in the other direction. Fixed properly this time: a separate,
explicit `where`/`which` probe for the binary's existence *before* running the real search, so the
real search's own exit code is trusted for what it actually means. Verified live both ways: a
genuinely-missing `rg` on this shell (PATH not yet refreshed after an earlier `winget install` —
correctly reported as not installed) and a `where git` probe against a definitely-present binary
(correctly found).

Checkpoint/undo verified live in a real scratch git repo, not just the offline suite: an
uncommitted pre-existing edit correctly swept into the auto-checkpoint before a run; `kirxil undo`
showing the real diff stat and reverting a file's content back to its pre-checkpoint version on
`y`; a second checkpoint left untouched after answering `n`; the correct "no checkpoint found"
message in a repo with no kirxil commits yet. New `cli/src/__tests__/checkpoint.test.ts` runs
against a real temporary git repo (real `git init`/`commit`/`reset`, no mocking) rather than
faking git's behavior, the same way the CLI's own `git diff`/`git status` commands are trusted to
just shell out for real. CLI: 32/32 tests pass (up from 27), `tsc --noEmit` clean.

## PRD §33's command surface — `ask`/`explain`/`analyze`/`generate`/`refactor`/`debug`/`test`/
## `review`, plus `git log`/`branch` and `doctor`

Continuing straight through the PRD, same session. §33 lists 22 subcommands; before this,
`kirxil` only had `run` as a general-purpose one. Added the 8 that map cleanly onto "run one goal
with a verb-specific instruction" (`cli/src/verbs.ts`) — each is the exact same
`runInstruction()`/`runOnce.ts` pipeline `run` already uses, so every one of them automatically
gets the live transcript, the Permission Engine pause, and the pre-run checkpoint for free, with
no new plumbing. The only real difference per verb is the instruction text: `ask`, `explain`,
`analyze`, and `review` explicitly tell the model not to create/edit/delete anything (real
instruction text — a request, not an enforcement mechanism, same trust model as any other goal);
`review` specifically asks it to look at `git diff` and tag findings HIGH/MEDIUM/LOW per §28's
`review` spec. Also added: `kirxil git log`/`git branch` (§28's "Commits"/"Branches", alongside
the existing `diff`/`status` — `blame` still isn't built), and `kirxil doctor` — session status,
whether the backend actually answers (distinguishing a real connectivity failure from a merely
expired/invalid session via the 401 specifically, after live-catching the generic version of this
message being actively misleading — see below), whether `git`/`rg` are genuinely on `PATH`, and
whether the current directory is a git repo checkpoints can use.

**A second real, live-caught bug, found *by* live-testing `doctor`**: the JWT this session's own
saved CLI credentials held had — by sheer coincidence of how long this session had been running —
expired literally around the same moment `doctor` was first run against it. `doctor`'s backend
check originally reported that as `"✗ Backend not reachable: Could not validate credentials"`,
which is wrong in a meaningful way: the backend *was* reachable and responding; the session was
just invalid. Fixed by checking `ApiError.status === 401` specifically and reporting "session is
invalid or expired — run `kirxil login` again" instead of the generic not-reachable message,
verified against both a real expired token and a real fresh one (see below).

**Live verification, real backend, real accounts** — the existing session's own token had expired
mid-session (see above), and its real password isn't something this agent has or should guess at,
so a throwaway account was registered directly against `POST /auth/register` for testing, used by
temporarily swapping `~/.krixil/credentials.json` (the *existing* file backed up first, restored
byte-for-byte afterward — never overwritten without a way back): `doctor` correctly flipped from
the misleading 401 message to "backend reachable and responding" against the fresh token;
`git log`/`git branch` against this repo's own real history/branch; `kirxil review` in a real
scratch git repo with a genuine uncommitted diff (an unchecked division, an unchecked dict lookup,
a hardcoded secret) — correctly auto-checkpointed, correctly scoped to the real subfolder via
`dirFromCwd` (an earlier manual test that passed `--dir .` explicitly instead of omitting it
incorrectly targeted `HOST_ROOT` itself, not the launch directory — a real difference in what `.`
means as a *computed* default versus a *literal* override, not a bug, but worth remembering when
testing by hand); `kirxil ask` triggering a real, correctly-HIGH-risk-gated `host.run_command`
pause. Also reconfirmed, unprompted, a known and already-documented limitation from earlier in
this track: the local `llama3.1:8b` model sometimes narrates a plan in prose instead of making a
real structured tool call on multi-step goals, and sometimes reaches for the sandboxed `code.*`
tool family instead of `host.*` even when the goal text says to use `host.*` — real model-quality
noise, not a regression from this session's changes, and not something prompt-engineering inside
one verb's template can reliably fix (`SYSTEM_PROMPT` is shared across every client). CLI: 40/40
tests pass (up from 32 — new `cli/src/__tests__/verbs.test.ts`), `tsc --noEmit` clean.

## `.kirxil.yml` project config (PRD §34) and an honest look at Model Router (§30)

Continuing through the PRD. §34 shows a fairly large YAML shape (`project`, `model`,
`agent`, `permissions`, `sandbox`, `memory`); built a deliberately small, honest slice of it
instead of all of it — `cli/src/projectConfig.ts` discovers `.kirxil.yml` by walking up from the
current directory the way `git` finds `.git`, and reads three fields: `project.name` (shown in
the interactive banner in place of the folder name), `model.default` (used unless `--model`/
`/model` explicitly says otherwise — real precedence: flag > config > `"auto"`), and
`agent.max_iterations`, forwarded as a new `AgentRunRequest.max_steps` field.

That last one touches the backend for real, not just the CLI: `create_agent_run`
(`app/agents/service.py`) now takes an optional `max_steps` and applies
`min(max_steps, settings.agent_max_steps)` — a client-requested budget can only ever *tighten*
the deployment's own configured ceiling, never raise it, so a project's own config file can't
become a way to bypass the operator's resource limit. New migration-free field (no new column;
`AgentRun.max_steps` already existed, this just lets a request influence what gets written there)
— two new backend tests cover both directions: a smaller requested budget is honored, a larger
one is silently clamped back down.

**What's deliberately not built, and why, matters as much as what is** — this is exactly the kind
of PRD section where padding out every field with something-that-looks-like-it-works would be
easy and wrong:

- `model.coding`/`model.reasoning` (§30's task-based auto-routing, "Reasoning"/"Coding"/"Fast"/
  "Vision"/"Local"): this deployment has exactly two real local Ollama models
  (`llama3.1:8b`, `qwen2.5:7b`, checked live via `/api/tags` — no vision-capable model at all) and
  no benchmark data saying either one is actually better at a given task type. Inventing that
  mapping anyway would be a fabricated capability claim, the same failure mode
  `app/ai/catalog.py`'s own "no fabricated catalog entries" rule already exists to prevent
  elsewhere in this codebase. `model.default` is the honest version: the user's own informed
  choice, not a guess dressed up as intelligence.
- `agent.max_retries`: there's no "retry" concept in the current agent loop distinct from a step
  — mapping this onto something would mean inventing that distinction just to have a field to
  point it at, not implementing something that already has a real shape.
- `permissions:` (per-action read/write/execute/network/git allow/ask policy): this would mean a
  client-supplied YAML file can change what the Permission Engine auto-approves or blocks — a real
  security-policy decision (could a project quietly set `execute: allow` and remove the HIGH-risk
  pause `host.run_command` just got wired up to earlier this session?), not a side effect that
  should ride along with "add a config file." Left out deliberately, not an oversight.
- `sandbox:`/`memory:`: `host.*` is unsandboxed by design already (see "Real host-folder access"
  above); memory is already a real per-*user* server-side setting (`app/memory/`), not a
  per-project one — neither needs a new config surface.

Verified live against the real backend, not just the offline suite — and without touching the
user's own saved session, which had already been swapped out and back once earlier this session
for the same reason (see "PRD §33's command surface" above): registered a second throwaway
account, wrote a real `.kirxil.yml` (`model.default: qwen2.5:7b`, `agent.max_iterations: 2`,
`project.name`), ran `kirxil run "say hi"` with no `--model`, and queried the created run directly
against the backend — confirmed `model_id: "qwen2.5:7b"` and `max_steps: 2`, both genuinely
sourced from the file, not just plausible-looking output. Re-ran with `--model llama3.1:8b` and
confirmed the flag overrode the config's default while `max_steps` still came from it — the real
precedence, not just the intended one. Backend: 160/160 tests pass (up from 158; two new tests in
`test_agents.py` covering both the honored-smaller-budget and clamped-larger-budget cases), ruff
and mypy clean. CLI: 46/46 tests pass (up from 40 — new `cli/src/__tests__/projectConfig.test.ts`),
`tsc --noEmit` clean.

## A real Anthropic (Claude) model provider — and why "connect to Claude Code" isn't the right frame

User asked to move off the two local Ollama models going forward and use "Claude Code" and
"Kimi K3" instead. Two real, separate things happened here, worth being precise about because
they're easy to conflate:

**Claude Code (the product this agent's own conversation is happening inside) isn't an API a
backend can connect to.** It's Anthropic's own CLI coding agent — an end-user application, not a
model-serving endpoint with a stable contract for third parties to call into. There's no
integration that makes `services/ai-service` "talk to Claude Code" as such. What *is* real and
buildable is Anthropic's actual product for this: the **Claude API** (Messages API,
`api.anthropic.com`) — the same models Claude Code itself runs on, reachable directly. That's what
got built: `app/ai/anthropic_provider.py`, a new `AnthropicModelProvider` implementing the same
`ModelProvider` interface `CloudModelProvider` already does for `"openai"`/`"ollama"`
(`generate`/`stream`/`tool_call`/`embeddings`/`health_check`), registered in `app/ai/router.py` as
`MODEL_PROVIDER=anthropic`.

Not built on `CloudModelProvider` the way `"openai"`/`"ollama"` are — Anthropic's Messages API
genuinely isn't OpenAI-compatible: the system prompt is a top-level `system` field, not a
`role="system"` message (`_split_system` lifts it out); auth is `x-api-key` +
`anthropic-version` headers, not `Authorization: Bearer`; tool use comes back as `content` blocks
(`type: "tool_use"`) inside the message, not a separate `tool_calls` array; there's no
`/embeddings` endpoint at all, so `AnthropicModelProvider.embeddings()` delegates to an injected
Ollama-backed provider instead (`app/ai/router.py` wires the same one `"ollama"` itself uses) —
RAG/knowledge search keep working even with `MODEL_PROVIDER=anthropic`, regardless of which model
answers chat/agent turns. New settings: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default
`claude-sonnet-5`), `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_VERSION`, `ANTHROPIC_MAX_TOKENS` — see
`.env.example`. `ModelRouter.get_provider()` raises a clear error if `MODEL_PROVIDER=anthropic`
is set with no key, matching the existing `"openai"` behavior exactly.

**"Kimi K3" needed a real check before building anything specific for it.** Moonshot AI's Kimi
models (K1/K1.5/K2, as far as this agent is aware — "K3" isn't a name it can confirm exists) are
served over an API Moonshot itself documents as OpenAI-compatible. If that's accurate, Kimi needs
**no new code at all** — the existing `"openai"` provider already works against any compatible
endpoint by construction (`CloudModelProvider`'s own docstring: "works against api.openai.com or
any endpoint that speaks the same shape"), so pointing `OPENAI_BASE_URL` at Moonshot's endpoint
with a real Moonshot API key and the exact model name is the whole change — documented in
`.env.example`. This is stated as "should work based on Moonshot's own documented compatibility,"
not "verified" — there's no Moonshot API key available to actually call it live and confirm.

**The one thing this session genuinely cannot do**: obtain, generate, or otherwise "find" a real
API key for either provider. That's not a missing feature — there is no legitimate mechanism by
which an API key materializes without the account holder creating it (console.anthropic.com for
Claude, Moonshot's own platform for Kimi) and handing it over. The code on both paths is real,
tested, and ready to work the moment a genuine key is set in `.env` — that's the actual, complete
extent of "connecting" that's possible from this side.

**Verification**: 10 new tests (`tests/test_anthropic_provider.py`) against `respx`-mocked
Anthropic responses — content/usage parsing, the system-message extraction, SSE delta streaming,
tool-use block parsing, embeddings delegation to an injected fake provider, and the real
`x-api-key`/`anthropic-version` headers (explicitly asserting *no* `Authorization` header is
sent, since that's the OpenAI-shaped mistake this class exists to avoid). 3 more
(`tests/test_ai_router.py`) cover the missing-key error, successful resolution with a key present,
and the catalog entry naming the configured model — including cleaning up `ModelRouter`'s
module-level instance cache after the test, since leaving a closed real `httpx` client cached
there would silently break whichever test happened to resolve `"anthropic"` next. No live call to
real Anthropic (or Moonshot) servers was possible without a real key — that's the honest boundary
of what "verified" means here, unlike this session's other work against the actually-running local
stack. Backend: 173/173 tests pass (up from 160), ruff and mypy clean.

## Closing the last two MVP gaps: `edit_file` and `search_files` (PRD §37)

User asked to finish the PRD's own defined stages before moving on. §37's MVP checklist names
10 items; 8 were already real. The remaining two — **File edit** (distinct from File write) and
**Code search** — turned out to be genuine, concrete gaps, not something already covered under a
different name: `host.write_file`/`code.write_file` only ever overwrite a file wholesale (the
model has to reproduce the entire file from memory to change one line, wasting tokens and risking
silently dropping unrelated content), and nothing let the *agent itself* search file contents by
pattern — `kirxil search` (ripgrep) is a CLI-only local passthrough the agent never sees; the only
tools it had were `list_files` (names only) and `read_file` (one file at a time), making anything
like "find every place X is used" expensive and slow on a real codebase.

**`host.edit_file` / `code.edit_file`** (`app/tools/host_tools.py` / `code_tools.py`): a
Claude-Code-style precise edit — `old_string`/`new_string`, and `old_string` has to appear
*exactly once* in the file or the call fails with a clear error (not found, or "appears N times,
add more context") instead of guessing which occurrence was meant. `host.edit_file` reads via
`host-runner`'s existing `GET /files/content`, does the replace in Python, writes back via its
existing `POST /files` — no new `host-runner` endpoint needed for this one. Same MEDIUM risk tier
as `write_file` (see that tool's own comment on why approval stays off for file mutations here).

**`host.search_files` / `code.search_files`**: real recursive regex search, LOW risk (read-only).
Deliberately *not* a shell-out to `rg` — this service already got burned once this session by a
tool whose correctness depended on an external binary actually being on `PATH` (`kirxil search`'s
own history, above) — so this is stdlib-only: `os.walk` + `re`, skipping `node_modules`/`__pycache
__`/`venv`/`dist`/`build`/dot-directories, treating a `UnicodeDecodeError` on read as "this is
binary, skip it" rather than erroring, and capping results at 200 so one broad pattern over a
large tree can't return an unbounded response. `code.search_files` needed nothing beyond a new
function in `app/workspace/fs.py` (same process, direct filesystem access, like `code.*`'s other
tools already do). `host.search_files` needed a genuinely new endpoint —
`services/host-runner/app/fs.py`'s `search_files()` plus `GET /search` in `main.py` — which meant
this was also the moment `host-runner` got its **first test suite ever** (`services/host-runner/
tests/`, 13 tests: `test_fs_search.py` against real temp directories and real files — recursive
search, directory-skip rules, binary-skip, subdirectory scoping, invalid-regex handling, the
result cap — and `test_main_search_endpoint.py` for the HTTP layer, via FastAPI's `TestClient`).
`host-runner` had zero tests before this, for every tool it's had since the start of this track —
worth naming plainly, not glossing over.

Also updated: `cli/src/goal.ts`'s `TOOLS` constant (the CLI's own goal-framing text) now names
both new tools so the model is actually told they exist, not just left to discover them via the
tool schema alone; `cli/src/render.ts` gained `Edit(path)`/`Search(pattern)` summaries and a
`describeObservation` case for search results (`N matches`, each shown as `path:line: text`,
capped and "…and N more" past `MAX_LISTED_ENTRIES`, same pattern `host.list_files` already uses).

**Verified live against the real running stack** — real `host-runner` (restarted to pick up the
code; a stale duplicate process from earlier in the session was found and killed first), real
files: `host.search_files` found a real match with the correct line number; `host.edit_file`
inserted a real, correctly-placed code block into a real file, leaving the rest byte-for-byte
untouched (confirmed by re-reading the file after); a full `kirxil run` end to end through the
actual agent loop showed `⏺ Search(divide)` / `⎿ 1 match` / the real matched line, rendered
exactly as designed. Used one more throwaway registered account for this (same reasoning as the
Permission Engine and command-surface verification earlier — the saved session's real password
isn't something to guess at); the user's own credentials file was backed up and restored
byte-for-byte again afterward. Backend: 183/183 tests pass (up from 173 — new `test_host_tools.py`
and `test_code_tools.py` coverage for both new tools on both paths), ruff and mypy clean.
`services/host-runner`: 13/13 tests pass (new suite). CLI: 51/51 tests pass (up from 46),
`tsc --noEmit` clean.

This closes every item on §37's MVP checklist. What's left in the PRD past this point (§38 V0.2
onward — Project Brain, autonomous agent orchestration, the full engineering platform, V1.0) is
explicitly staged as later phases in the PRD's own document, not MVP scope.

## Two more real, small gaps closed: `delete_file` and `git blame` — and a real test bug this uncovered

User asked to keep finishing what the PRD itself flags as gaps. Two were already named explicitly
in this document from the previous pass: `host-runner` already had a real `DELETE /files`
endpoint (`services/host-runner/app/fs.py`'s `delete_file`) with no agent-callable tool wired to
it, and §28's Git Intelligence table names `blame` as something Kirxil should have, sitting
unbuilt next to the `status`/`diff`/`branch`/`history` commands that already existed.

**`host.delete_file` / `code.delete_file`** (`app/tools/host_tools.py` / `code_tools.py`): HIGH
risk, not MEDIUM like `write_file`/`edit_file` — a deliberate, different tier, reasoned through
explicitly in the tool's own comment: an overwrite or edit's previous content is still one more
write/edit away from being restored (the model can just put it back if asked), but a deleted file
is actually gone from this tool's own perspective — the only way back is the checkpoint safety
net (`kirxil undo`), not this tool undoing itself. That makes it the *second* real trigger for the
Permission Engine's pause-and-resume flow (`host.run_command` was the first) — useful proof the
mechanism generalizes correctly to a second, unrelated tool rather than having been built to fit
one specific case. `code.delete_file` also rejects deleting a directory, matching the existing
`document.delete` `IsADirectoryError` handling pattern already established elsewhere.

**`kirxil git blame <file>`**: the fifth real local git passthrough command
(`diff`/`status`/`log`/`branch`/`blame`), same shape as the others — except this one explicitly
surfaces `stderr` on failure rather than just printing empty `stdout`, since a blame failure (bad
path, file not tracked) is common enough in real use that silence would be confusing.

**A real, live-caught test bug, not a production bug**: adding `code.delete_file`/
`host.delete_file` broke two existing tests in `test_agents.py` — not because anything they
exercised stopped working, but because `MockProvider`'s tool-selection heuristic
(`app/ai/mock_provider.py`'s `_matches_tool`) picks the *first alphabetically-registered* tool
whose name contains any word also present in the goal text, and `code.delete_file`'s own name
words (`code`, `delete`, `file`) now collide with `document.delete`'s (`document`, `delete`) on
the shared word "delete" — with `code.delete_file` sorting first. `test_agent_stops_waiting_
approval_for_critical_tool_and_does_not_execute_it` didn't fail outright (its assertions weren't
specific enough to notice), which is the more concerning half of this: it silently started
exercising a HIGH-risk tool instead of the CRITICAL one its own name says it's testing, and would
have kept silently passing while testing the wrong thing indefinitely if
`test_approving_agents_pending_tool_actually_executes_it` and `test_agent_handles_a_failed_tool_
call_without_crashing` hadn't failed loudly enough to force a look. Fixed by rewording the
affected goals from `"please delete document {id}"` to `"please get rid of document {id}"` —
deliberately avoiding the now-ambiguous word "delete" and relying on "document" (unique to
`document.delete` among every currently-registered tool) instead, so the mock's word-matching
resolves the *intended* tool deterministically regardless of what else gets registered
alphabetically before it later. Not a MockProvider bug worth "fixing" more deeply — it's
explicitly documented as a crude, deterministic stand-in, not real NLU — but a reminder that any
test relying on its keyword matching needs a genuinely unique anchor word, not just a
plausible-sounding one.

**Verified live** against the real running stack: `host.delete_file` via direct tool execution —
confirmed the file still existed after the pending-approval response, and was actually gone only
after approving; `kirxil git blame` against a real tracked file in this repo's own history
(showing real commit hashes, author, and dates) and against a real untracked file (a clear
`fatal: no such path ... in HEAD` instead of silent empty output). Backend: 187/187 tests pass (up
from 183 — the two fixed tests plus 4 new ones covering `delete_file`'s approval/rejection on both
`host.*` and `code.*`), ruff and mypy clean. CLI: 53/53 tests pass (up from 51), `tsc --noEmit`
clean.

## Plan Mode and `memory` — closing two more named PRD gaps

Continuing through the PRD. Two more items had real, bounded, honest paths to close: §19 Plan
Mode (`kirxil plan`) and §33's `memory` command — the second one notable because it needed
essentially no new backend work at all.

**`kirxil plan <goal>`** (`cli/src/verbs.ts`, now a 9th verb alongside `ask`/`explain`/`analyze`/
`generate`/`refactor`/`debug`/`test`/`review`): the same `runInstruction`/`runOnce.ts` pipeline
every other verb uses, with a goal template that asks the model to investigate, then answer in
the PRD's own format — "PLAN" followed by numbered steps, then a rough files/LOC estimate if it
can reasonably make one from what it read — and explicitly not to implement anything. One honest
simplification from the PRD's implied version: there's no separate "review this plan, then
auto-execute it" handoff state — `kirxil plan` stops after producing the plan, same as `analyze`/
`review` stop after their own read-only pass; turning any of it into real changes is a plain
`kirxil run`/`generate`/`refactor` call afterward with that plan (or a piece of it) as the goal.
Building a genuine two-phase plan→approve→execute state machine would be new, real scope — this
is deliberately the simpler, honest version of what §19 asks for, not a shortcut passed off as
the full thing.

**`kirxil memory list/add/forget/status/on/off`**: the PRD's §33 command surface names `memory`,
and it turned out the entire backend for it already existed and had for a while — `app/memory/`'s
long-term memory system (durable, per-user facts auto-extracted from completed chat/agent turns),
built in an earlier phase of this project, already exposed via `GET`/`POST /memory`,
`DELETE /memory/{id}`, `GET`/`PATCH /memory/settings`, and already used by the web app. This pass
added zero backend surface — just `cli/src/api.ts`'s thin client methods and the command group in
`cli/src/index.ts`, following the exact same `requireApi()`/`resolveClientOrEnv()` pattern every
other authenticated command already uses (pulled `requireApi()` out as a small helper once
`memory`'s six subcommands needed the "resolve a client or bail with the same message" shape,
rather than copying it a sixth time — `models` was refactored to use it too, for the same reason
it existed inline six times before). One real, honest scope note: the PRD's own §15 framing
("Architecture decisions", "Coding conventions", etc.) implies a structured *project* knowledge
base — what actually exists is simpler, per-*user* facts, not project-scoped; the CLI command just
gives terminal access to what was already really there, it doesn't change what that memory system
actually models.

**A real, live-caught bug while testing `plan`, unrelated to `plan` itself, not fixed**:
reconfirmed the same known `llama3.1:8b` limitation from earlier in this track — on a
multi-step planning goal, it narrated a second tool call in prose (`code.search_files` with a
regex `input`) instead of making a real structured call, and reached for the sandboxed `code.*`
namespace instead of `host.*` even though the goal text says to use `host.*`. Named plainly again
because it's the same real, pre-existing model-quality ceiling, not something specific to the new
verb — `plan`'s own goal-building, checkpoint integration, and first tool call all worked
correctly before the model's own narration habit took over.

**Verified live**: `kirxil memory list/add/forget/status/on/off` against the real backend, in
that order, watching each state change take effect for real (added a memory, saw it listed with
its real id, forgot it by that id, saw the list go empty again; toggled memory off and on and
watched `status` reflect each change) — using a still-valid throwaway account from an earlier
verification pass in this same session, the real session backed up and restored again afterward.
`kirxil plan` produced a real goal (visible in its own `›` echo) matching the PLAN-format
instruction correctly, and correctly triggered the real pipeline (tool schemas, checkpoint check)
before the model's own multi-step narration limitation took over — the same limitation already
documented above, not something new. Backend unchanged (no new endpoints — pure CLI-side, using
what already existed). CLI: 59/59 tests pass (up from 53), `tsc --noEmit` clean.

## `kirxil config` — closing the last easy gap in the §33 command surface

Continuing through the PRD. `.kirxil.yml` (§34) had real logic behind it (`cli/src/
projectConfig.ts`) but no way to actually *see* what it resolved to short of reading the raw YAML
yourself and mentally re-deriving the fallback rules — a real, small, closeable gap, and the last
one in §33's command list that didn't need infrastructure this deployment doesn't have.

`kirxil config` (`cli/src/index.ts`) shows exactly two things: which file it found (walking up
from the current directory, same discovery `loadProjectConfig` already used — exported as a
standalone `findConfigFile` so the command could report the path even when parsing the file's
*contents* isn't what it needs to do), and each of the three implemented fields
(`project.name`/`model.default`/`agent.max_iterations`) with a plain-language description of the
fallback in effect when a field isn't set, rather than silently defaulting with nothing to check
against. No new backend surface — reuses `loadProjectConfig` as-is.

Verified live in both states: no `.kirxil.yml` anywhere up the tree (correct "not found" message
plus the three real fallback descriptions), and a real file with all three fields set, run from a
*nested subdirectory* two levels below where the file actually lives — confirming the walk-up
discovery `findConfigFile` shares with `loadProjectConfig` resolves to the same real path in both
directions, not just when standing in the project root. 2 new tests for `findConfigFile`
specifically (previously only exercised indirectly through `loadProjectConfig`'s own tests).
CLI: 61/61 tests pass (up from 59), `tsc --noEmit` clean.

This closed everything in §33's command surface that was honestly closeable without new
infrastructure at the time — 14 of 22 real. What remained (`build`, `agent`, `swarm`, `deploy`,
`monitor`, `project`, `plugin`) each needed something this deployment genuinely doesn't have — or
so it seemed until a second look at `build` specifically (next section).

## `kirxil build` (§20) and an honest look at `--auto` (§21)

Continuing through the PRD. `build` had looked like it belonged in the "needs infrastructure"
pile alongside `agent`/`swarm`/`deploy` — on a second look, it doesn't; it's the same
goal-template shape every other verb already uses, just a more demanding instruction. §20's own
spec is a workflow, not a subsystem: "PLAN → IMPLEMENT → TEST → REVIEW." `kirxil build <goal>`
(`cli/src/verbs.ts`, a 10th verb) instructs the model to work through and name all four phases in
one run — plan briefly, implement for real, run (or write and run) tests and fix a genuine
failure's real cause rather than just reporting it, then review its own actual diff before
declaring done. Not read-only, unlike `plan`/`ask`/`explain`/`analyze`/`review` — this one is
meant to actually build the thing, so it gets no special restriction beyond what `run` already
has (the Permission Engine pause on `host.run_command`, the pre-run checkpoint).

**§21 Auto Mode turned out not to need a flag at all.** Its own spec says autonomous workflow,
but HIGH-risk actions still need approval and dangerous actions stay blocked — read closely,
that's not a *toggle* description, it's a description of behavior the Permission Engine (§17)
already provides unconditionally: LOW/MEDIUM tools already run with zero pausing, HIGH already
pauses for a real approval, nothing reaches CRITICAL/BLOCK yet. There's no "ask about everything"
mode for a `--auto` flag to opt out of — building one would toggle nothing real, the exact kind of
cosmetic command this project has avoided everywhere else. Documented as closed by observation,
not by new code, in both `kirxil-cli-prd.md`'s §21 status note and `cli/README.md`.

**Verified live** against the real running stack (a fourth throwaway account this session, same
reasoning as every prior one — the real session backed up and restored again afterward): a real
`kirxil build` goal against a real two-line Python file. The goal text matched the four-phase
template exactly (confirmed in the CLI's own echoed `›` line); the run reached the backend, ran,
and completed — but made **zero real tool calls** (`tool_call_count: 0`, confirmed directly
against the agent run's own record via the API, not inferred from the printed transcript), the
model choosing to narrate all four phases as prose in one response instead of calling tools step
by step. This is the same already-documented `llama3.1:8b` multi-step-narration ceiling from
earlier in this track, reconfirmed rather than newly discovered — worth naming plainly again
rather than only showing a cherry-picked successful run, since an honest account of `build`
includes that its real-world reliability is bounded by this local model's own capability on
demanding multi-step goals, not by anything about the verb itself. CLI: 62/62 tests pass (up from
61), `tsc --noEmit` clean.

## Deliberately out of scope for this first pass

A real diff/IDE view, streaming command output (results return only after the command finishes —
see above, still true even with step-by-step progress now live), multi-workspace/multi-project
support (one workspace per tenant), and a true per-tenant volume-subpath mount (today
`sandbox-runner` mounts the whole shared volume and relies on `working_dir` to scope a command to
the tenant's own subdirectory — a real Docker Engine volume-subpath mount would tighten this
further once this app is more than single-tenant, but isn't guaranteed to be supported by every
installed Engine version). For the host-runner path specifically: picking a different `HOST_ROOT`
than `D:\` still requires editing `.env` and restarting the service (no dynamic re-rooting), and
`host-runner` has to be started manually each session (no Scheduled Task wired up yet, unlike
`training/`'s equivalent). Approval for `code.*`/`host.write_file` remains deliberately off, per
the user's explicit choice when this redesign was scoped; `host.run_command` is the one exception,
now HIGH risk and approval-gated for real (see "Permission Engine wired end-to-end" above) — that
line no longer describes the whole `host.*` surface, just what's left of it.

## Visual overhaul: the CLI's "AI operating system" look, real subset only

The user shared a very detailed, prescriptive mockup for `kirxil` — boxed panels, a multi-agent
orchestrator tree, a "KIRXIL SWARM" graph, a `kirxil brain` command with fabricated indexing
stats, security/deploy centers, a persistent context bar, "Always allow for project/session"
permission memory, a self-healing loop with attempt counters — modeled after "Claude Code +
Blackbox CLI, but with deeper visual and orchestration features." About half of it describes UI
polish over data that's already real (plan text, tool calls, diffs, approve/reject, git state,
run history); the other half describes capabilities that don't exist anywhere in Krixil today —
no multi-agent orchestrator (still one generic agent loop), no AST/symbol/dependency indexer, no
vulnerability scanner, no deploy target/environments, no swarm mode, and no backend concept of a
remembered permission decision. This pass builds the real half in the mockup's own visual
language and explicitly does not touch the fabricated half — building a tree of agent names that
aren't really running independently, or a "12,482 files indexed" stat with no indexer behind it,
would be exactly the kind of decorative, non-functional UI this project has avoided everywhere
else.

**What shipped, all real data:**

- **Richer banner** (`ui/Banner.tsx`) — a real top-level file/folder count for the current
  directory (a cheap `readdirSync`, not a recursive walk implying a deep index that doesn't
  exist) and a real online/offline dot from an actual `api.listModels()` probe at startup.
- **Real diff rendering for edits** (`render.ts`'s `describeObservation`, now taking the tool
  call's own `old_string`/`new_string` via a new `buildToolCallArgsLookup` step-number lookup) —
  `host.edit_file`/`code.edit_file` observations show an actual `-`/`+` block with real line
  counts instead of a flat "Edited". One implementation, wired into both `ui/Transcript.tsx` (Ink)
  and `runOnce.ts` (plain-text `kirxil run`), so the two renderers never drift.
- **Permission prompt redesign** — the same real `y`/`n` approve/reject, now shown with its real
  risk level in a bordered panel (red border for the one tier that would warrant it). CRITICAL
  risk — unreachable by any registered tool today, but handled in case one is ever added — asks
  for a real typed `CONFIRM` instead of a keypress, in both the Ink app and `runOnce.ts`.
  Deliberately not built: "Always allow for project/session" — needs new backend policy storage
  (remembering a decision across executions), a real security-relevant decision on its own, not
  bundled into a visual pass.
- **Derived step-state labels** (`render.ts`'s `describeInFlightStep`/`findInFlightToolCall`) — a
  short "Running tests…"/"Searching…"/"Editing…" label for whatever tool call is actually in
  flight right now, inferred from the real tool name and command text, shown in the REPL's working
  indicator.
- **Real status bar** (new `ui/StatusBar.tsx`) — real tool-call count, real test-attempt count,
  and real `git diff --stat`-derived change stats (`checkpoint.ts`'s new
  `workingTreeChangeSummary`/`parseShortstat`) for the run in progress, polled every 2s.
- **`kirxil init`** — interactively scaffolds a real `.kirxil.yml` (project name, `model.default`
  picked from the real `kirxil models` list, optional `agent.max_iterations`), asks before
  overwriting an existing file.
- **`kirxil sessions`** — lists real past agent runs newest-first via a new `listRuns()` client
  method against the existing `GET /agents` endpoint (`list_agent_runs`), already used by the web
  app's Agents page but never previously exposed from the CLI.
- **Real test-attempt counting** (`render.ts`'s `countTestAttempts`) — counts `run_command` tool
  calls whose command text looks like a test invocation (pytest/npm test/vitest/jest/go test/...),
  surfaced in the status bar and in `runOnce.ts`'s final summary line — a real count over real
  commands, not a fabricated self-healing-loop attempt counter.
- **`kirxil plan` gets a bordered `KIRXIL PLAN` panel** (`render.ts`'s `planPanelLines`, new
  `ui/PlanPanel.tsx`) around the model's real plan text, plus a real follow-up: in a real terminal
  only (never piped/scripted), pressing Enter after a completed plan runs `kirxil build` with that
  exact same goal; anything else skips. `/plan <goal>` does the same inside the interactive REPL.
  Genuine chaining of two commands that already existed independently — not a new planning engine.

**Explicitly not built, and why** (unchanged from the plan): the multi-agent orchestrator tree and
swarm mode (one real agent loop, no independently-running named agents to render), `kirxil brain`/
Project Brain (PRD §13, no AST/symbol/dependency indexer — separate, much larger future phase),
`kirxil security` (no vulnerability scanner), `kirxil deploy`/`kirxil logs` (no deploy target, no
environments, no "production" concept anywhere in this deployment), and "Always allow for
project/session" (needs new backend policy storage).

No backend changes — pure CLI-side rendering plus one new thin client method (`listRuns()`)
against an endpoint that already existed. CLI: 84/84 tests pass (up from 62), `tsc --noEmit`
clean. **Verified live** against the real running stack (a fresh throwaway account, same
reasoning as every prior verification this track — the real saved session backed up and restored
afterward): `kirxil init` in a scratch git repo (created directly under the real `HOST_ROOT`,
`D:\`, since host.* tools can't reach outside it) round-tripped correctly through `kirxil config`;
a real `kirxil run` goal against a real file produced a real `Edited (+1/-1)` diff showing the
actual before/after lines, and the file's real content matched; `kirxil sessions` listed that same
real run, matching `GET /agents` exactly. A real HIGH-risk `host.run_command` pause was also
exercised through the restyled panel — it showed the real risk level, paused for a real `y`/`n`,
and resumed the run correctly after approval, ending in a real final response. A real
`kirxil plan` goal produced a real bordered panel around the model's actual multi-step plan text.

One piece **not** independently live-verified end to end: the plan → `[Enter]` → `kirxil build`
handoff itself. It's gated on `process.stdin.isTTY`, correctly and cleanly (confirmed live — no
hang, clean exit) skipped when driven from a piped child process, since neither this sandbox's
shell nor `winpty` can present a real TTY to a non-interactively-launched process here. The
handoff's own execution path is a second call into the exact same `runGoalOnce` already exercised
successfully above (the HIGH-risk approval run), so it isn't untested logic — just wiring this
environment couldn't drive through a real keypress. Worth a real human check in an actual
terminal before leaning on it.
