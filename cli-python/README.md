# krixil-cli (Python) — superseded by `cli/` (Node.js/TypeScript)

> **This is no longer the active CLI.** Rebuilt in Node.js/TypeScript against the CLI's own PRD —
> see [`../cli/README.md`](../cli/README.md) and
> [`docs/architecture/coding-agent.md`](../docs/architecture/coding-agent.md)'s "`cli/` rebuilt in
> Node.js/TypeScript against a formal PRD" section. Kept here for reference, not deleted — the
> design reasoning below (same backend contract, same goals) still applies to the rewrite.

# krixil-cli — a terminal coding agent for your own Krixil backend

Same idea as Claude Code, Aider, or Blackbox's CLI — but talking to `services/ai-service`, not a
third-party model host. Real, unsandboxed access to whatever folder you launch it from (via
`services/host-runner` — the exact same `host.*` tools and live-streaming Agent-run backend the
web app's Code page uses, see [`docs/architecture/coding-agent.md`](../docs/architecture/coding-agent.md)),
rendered as a live `⏺ Tool(args)` / `⎿ result` transcript identical to
[`step-view.tsx`](../apps/web/src/components/agent-run/step-view.tsx)'s.

## Setup

```powershell
cd cli
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

This installs a real `krixil` command (via `[project.scripts]` in `pyproject.toml`) into the
venv's `Scripts/` — add that to your `PATH`, or just call it as `.venv\Scripts\krixil.exe` /
activate the venv first.

`services/ai-service` (Docker) and `services/host-runner` (native — see its own README) both need
to be running; `krixil` is a client of both, not a replacement for either.

## Log in

```powershell
krixil login
```

Asks for the api base URL (defaults to `http://localhost:8000/api/v1`), your workspace slug,
email, password, and the real folder `host.*` tools operate under on this machine (your
`HOST_ROOT`, e.g. `D:\`) — saves the session to `~/.krixil/credentials.json` so you only do this
once. For scripted/non-interactive use instead, set `KRIXIL_TENANT_SLUG`, `KRIXIL_EMAIL`,
`KRIXIL_PASSWORD` (same three variables `training/client.py` already reads) — `krixil` falls back
to those when nothing's been saved via `login`.

## Use it

```powershell
cd D:\some\real\project
krixil
```

Drops into an interactive prompt, scoped to whatever folder you're standing in (computed relative
to your configured `HOST_ROOT` — outside that tree entirely, it falls back to the root folder,
since `host.*` tools can't reach anywhere else regardless). Type a goal, watch it run live, `Ctrl+C`
to stop a run in progress (same `POST /agents/{id}/cancel` the web's "esc to interrupt" button
calls — it finishes whatever tool call is already in flight, then stops). `/model` lists and
switches models, `/cwd` shows the current folder, `/exit` quits.

```
› fix the bug where it crashes on empty input

⏺ Read(app.py)
  ⎿ Read 42 lines
     ...
⏺ Write(app.py)
  ⎿ Saved
⏺ Bash(pytest -q)
  ⎿ Exit 0
     3 passed in 0.41s

Fixed — the empty-input case now returns early instead of indexing into an empty list.
```

For scripting, `krixil run "<goal>"` runs one goal non-interactively and exits (`--model`, `--dir`
to override either default); `krixil models` just lists what's available.

## Tests

```powershell
pip install -r requirements-dev.txt
pytest -v
ruff format --check .
ruff check .
mypy krixil_cli
```

Fully offline (`pytest-httpx` mocks every HTTP call) — no running backend required to test the
CLI's own logic.

## What this is not

Not a second implementation of the agent loop — every goal still runs through
`services/ai-service`'s real `POST /agents/run`/`GET /agents/{id}/status`/`POST
/agents/{id}/cancel`, the same background-task-driven, live-streaming loop
`docs/architecture/coding-agent.md` documents. This is a client, the same way the web app's Code
page is — just a terminal one instead of a browser one.
