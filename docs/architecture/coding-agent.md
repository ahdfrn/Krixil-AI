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

## Deliberately out of scope for this first pass

A real diff/IDE view, streaming command output (results return only after the command finishes),
multi-workspace/multi-project support (one workspace per tenant), and a true per-tenant
volume-subpath mount (today `sandbox-runner` mounts the whole shared volume and relies on
`working_dir` to scope a command to the tenant's own subdirectory — a real Docker Engine
volume-subpath mount would tighten this further once this app is more than single-tenant, but isn't
guaranteed to be supported by every installed Engine version). For the host-runner path
specifically: picking a different `HOST_ROOT` than `D:\` still requires editing `.env` and
restarting the service (no dynamic re-rooting), and `host-runner` has to be started manually each
session (no Scheduled Task wired up yet, unlike `training/`'s equivalent).
