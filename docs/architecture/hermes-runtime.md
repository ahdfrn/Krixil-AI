# Hermes Runtime Integration

An alternate `AgentRuntime` for `kirxil run`/`build`/the interactive REPL — a real HTTP+SSE
client against Hermes's own documented "Runs API" (`NousResearch/hermes-agent`), never Hermes
imported as a Python dependency into `services/ai-service`.

## Why a separate service, not a library

Hermes was researched twice. The first pass concluded there was no safe integration surface at
all — that conclusion was outdated: Hermes genuinely ships `POST /v1/runs`, `GET /v1/runs/{id}`,
`GET /v1/runs/{id}/events` (SSE), `POST /v1/runs/{id}/approval`, `POST /v1/runs/{id}/stop`
(`gateway/platforms/api_server.py`/`api_server_runs.py` in the real repo — verified directly
against that source, not just its docs). But importing Hermes's own `agent/` package directly is
still not viable: its `pyproject.toml` exact-pins `pydantic==2.13.4`/`httpx==0.28.1`, which
directly conflicts with this service's own `pydantic==2.10.2`/`httpx==0.27.2` pins in the same
venv — the same class of problem `mcp==1.9.4`'s own pin was chosen specifically to avoid (see
`roadmap.md`'s Phase 6). A separate service reached over Hermes's real HTTP API sidesteps this
entirely, matching this codebase's own established pattern for `sandbox-runner`/`host-runner`/
`training` — each a backing service with its own dependency set, never merged into the main
backend.

## Architecture

```
kirxil (CLI) --runtime hermes
      │
      ▼
POST /agents/run  (services/ai-service)
      │
      ├─ runtime="native"  → run_agent_in_background (app/agents/router.py, unchanged)
      └─ runtime="hermes"  → run_hermes_agent_in_background (app/agents/hermes_runtime.py)
                                   │
                                   ▼
                          app/agents/hermes_client.py
                          POST /v1/runs, GET .../events (SSE), .../approval, .../stop
                                   │
                                   ▼
                          a real, separately-run Hermes instance
```

`AgentRun` gained two columns (migration `0018_agent_run_runtime`): `runtime` ("native" default,
"hermes" for a Hermes-proxied run) and `external_run_id` (Hermes's own `run_id` string). The
native loop (`app/agents/runner.py`) is completely untouched — `runtime` is a plain dispatch flag
`POST /agents/run` branches on once, not a forced shared interface, since the two runtimes'
real execution shapes (a direct DB loop vs. a remote SSE-consumption loop) are different enough
that forcing one would mean bending the native loop's working shape to fit an abstraction that
exists for exactly one other implementation.

## Event translation

`app/agents/hermes_runtime.py` translates Hermes's real SSE events into the exact same
`AgentStep` rows the native loop writes (via the now-public `record_agent_step`, shared with
`runner.py`), so the CLI's `Transcript.tsx` renders both runtimes identically with zero changes:

| Hermes event | Krixil effect |
|---|---|
| `tool.started` | `AgentStep(type="tool_call", ...)`, `tool_call_count += 1` |
| `tool.completed` | `AgentStep(type="observation", ...)` |
| `approval.request` | the permission bridge (below) |
| `run.cancelled` / stream end | `AgentRun.status` set to the real terminal state, final `AgentStep(type="final_response", ...)` |
| `reasoning.available`, `subagent.start`/`complete` | read, not persisted this pass |

## The permission bridge — Krixil's Permission Engine stays the single source of truth

Non-negotiable, explicitly confirmed requirement: a Hermes tool call is never auto-allowed and
never resolved through a second, parallel approval system. `classify_hermes_approval()` implements
the confirmed 3-tier policy:

1. **A real match against Krixil's existing destructive-command patterns**
   (`app/tools/risk_rules.py`'s `find_block_reason` — the same `rm -rf /`/`format C:` patterns
   `host.run_command` already blocks) → BLOCK outright, Hermes told `"deny"` immediately, never
   shown to a human, no `ToolExecution` row.
2. **An opaque request** (no usable tool name or actionable arguments, malformed argument JSON,
   or a command tool without a command) → auto-deny, same as above —
   "insufficient information to evaluate risk."
3. **Every other real, inspectable request** → a real `ToolExecution` row
   (`tool_name="hermes.<tool>"`, `risk_level="high"`, `status="pending_approval"`), the exact
   same audit-logged row a native HIGH-risk tool call creates. `AgentRun.status` becomes
   `"waiting_approval"`, and — critically — the CLI's approval prompt is the *same, unmodified*
   `POST /tools/executions/{id}/approve`/`reject` endpoint every other tool already uses. Approving
   tells Hermes `"once"` and re-subscribes its event stream
   (`resume_hermes_agent_in_background` — Hermes's own run never stopped server-side, only
   Krixil's consumption of it paused); rejecting tells Hermes `"deny"` and the run ends. Krixil's
   own approval UI only ever offers binary approve/reject for any tool (native or Hermes) — there
   was never a "session"/"always" option to withhold in the first place.

`app/tools/service.py`'s `approve_execution`/`reject_execution` gained one branch each: a
Hermes-bridged execution has no local Krixil `tool.handler` to run (Hermes itself executes the
tool), so approving it calls `resolve_hermes_approval(..., "once")` directly instead of
`_run()`. `app/tools/router.py`'s approve endpoint schedules `resume_hermes_agent_in_background`
instead of native `run_agent(resume=True)` when the resumed run's `runtime == "hermes"`.

Approval is not completion: the execution stays `running` with no completion timestamp until
the matching `tool.completed` event supplies its outcome. Missing results at stream termination
are recorded as failed/unknown, never assumed successful. Approval request IDs are forwarded.
Command checks include nested `args`/`arguments`/`input` objects and JSON-encoded arguments.
The CLI displays the complete escaped request and explicitly warns that remote scope is not
verified by Krixil; this heuristic policy is not filesystem confinement. Successful events omit
the error field, and the renderer also tolerates legacy `error: false` observations.

## Configuration

`HERMES_BASE_URL`/`HERMES_API_KEY`/`HERMES_TIMEOUT_SECONDS` (`app/core/config.py`) — empty
`HERMES_BASE_URL` means `runtime="hermes"` is rejected with a clear 400, never a silent fallback
to native. `docker-compose.yml` has a commented-out `hermes` service block (this repo doesn't
vendor a Hermes checkout) — uncomment and point `context:` at a real one to actually run it.

CLI: `--runtime <native|hermes>` on `kirxil run`, every verb, and the bare interactive REPL;
`.kirxil.yml`'s `agent.runtime` sets the project default. Precedence: `--runtime` > `.kirxil.yml`
> `"native"`, same shape as `--model`/`model.default`.

## Tests and verification

Offline: `tests/fixtures/hermes_fixture_server.py` is a real, scriptable HTTP+SSE server
implementing Hermes's real documented Runs API shape (verified against the real source) — same
"real fixture, not a mocked SDK" discipline this codebase already uses for MCP
(`tests/fixtures/mcp_test_server*.py`). `tests/test_hermes_client.py` (8 tests) and
`tests/test_hermes_runtime.py` (6 tests, including a full round trip through the real,
unmodified `/tools/executions/{id}/approve` endpoint) both run against it. Backend 295/295,
ruff/mypy clean. CLI 130/130, tsc clean.

**Not done this pass, explicitly**: installing or running a real Hermes instance (a third-party
installer decision that's the user's own call, independent of this integration's own safety —
see the earlier "don't pipe an installer to a shell unread" lesson in
`learning-and-memory.md`), swarm-per-child runtime selection, the ACP protocol, the TUI-gateway
JSON-RPC protocol (HTTP+SSE only, per the confirmed rollout plan), and persisting
`subagent.start`/`subagent.complete` as Krixil rows. **A real live-Hermes smoke test
(`kirxil run --runtime hermes "<goal>"` against a genuine running Hermes with a real
`API_SERVER_KEY`) is a manual follow-up once the user has one running** — not claimed done here.
