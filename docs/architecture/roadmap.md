# Roadmap

Each phase must be runnable and tested before the next one starts — no phase is scoped until the prior one is done.

- **Phase 0 — Foundation** (done): repo skeleton, FastAPI, Postgres/Redis/MinIO, config, structured logging,
  auth (register/login, JWT), tenant context + isolation, model abstraction + mock provider, streaming chat
  endpoint, Alembic migrations, offline test suite. See `phase0.md`.
- **Phase 1 — Real model providers + memory** (done): a real `CloudModelProvider` (OpenAI-compatible
  HTTP client), short-term conversation memory in Redis, per-tenant rate limiting, usage tracking. See `phase1.md`.
- **Phase 2 — RAG** (done): document upload/parsing/chunking/embedding, pgvector similarity search
  (HNSW), keyword full-text search (GIN), hybrid merge (RRF), citations in chat responses. See `phase2.md`.
- **Phase 3 — Tools & permissions** (done): tool registry/schema/permission/risk-based execution/audit
  trail, human approval workflow for HIGH/CRITICAL tools, 3 real tools (`knowledge.search`,
  `usage.get_summary`, `document.delete`). Business/POS tools (`sales.get_summary`, etc.) deferred until
  there's an actual external system to connect to. See `phase3.md`.
- **Phase 4 — Agents** (done): planner/executor/observer loop (`POST /agents/run`,
  `GET /agents/{id}/status`), step/tool-call/time budgets, real `tool_call()` function-calling on both
  providers, human-approval integration with Phase 3. Specialized agents (research, data analyst, coding)
  deferred the same way Phase 3's business tools were — real capabilities to connect first. See `phase4.md`.
- **Phase 5 — Evaluation, observability, hardening** (done, current): Prometheus metrics + Grafana
  dashboard + OpenTelemetry tracing (Jaeger), an AI evaluation harness with baseline/regression
  comparison, a GitHub Actions CI/CD pipeline (lint/typecheck/test/security/build/evaluate/smoke-test),
  and a full dependency security audit (59 known CVEs found and fixed down to 1 documented, accepted
  exception). Staging/production deploy automation deferred — no target infrastructure exists yet to
  deploy to; everything up to a verified, working container image is already automated. See `phase5.md`.

This closes out the original backend roadmap. **Addenda (2026-08-30)**, both in `phase1.md`:
(1) conversation rename (`PATCH /conversations/{id}`) and delete (`DELETE /conversations/{id}`),
plus a related tenant+user-scoping tightening on `GET /conversations/{id}`; (2) `GET /models` +
a `model` field on `ChatRequest` — today always resolves to the one real configured provider
(`id="auto"`), not a fabricated multi-model catalog, since `ModelRouter` has no concept of more
than one simultaneously-available model yet.
**Self-hosted AI via Ollama — done 2026-08-31**: closed the "second real model in the catalog" item
below, and — more fundamentally — gave Krixil an actual reasoning model instead of
`MODEL_PROVIDER=mock`'s keyword matcher, per the user's original goal of a private AI with no
third-party subscription. `MODEL_PROVIDER=ollama` reuses `CloudModelProvider` (refactored to
explicit config) against a natively-installed local Ollama; `qwen2.5:7b` and `llama3.1:8b` both
installed with real runtime switching, embeddings moved to `nomic-embed-text` (768-dim, migration
`0008_ollama_embedding_dim`). See `self-hosted-model.md`.

Later, not yet scheduled: fine-tuning (LoRA/QLoRA) pipeline, self-hosted inference via vLLM,
Kubernetes migration, staging/production hosts (needed before Phase 5's deploy automation can be
finished), a second role + requester/approver separation for tool approvals (needs an invite/
add-user endpoint first — see phase3.md), agent-run resume-after-approval (see phase4.md),
conversation pin/archive (needs a schema migration).

## Web app (`apps/web`) — separate phase track, own spec

Runs on its own 5-phase plan from a second master-prompt spec, unrelated to the backend phase
numbers above.

- **Web Phase 1 — UI, mock data** (done): full premium chat/workspace UI (layout, sidebar, chat
  home, chat interface, composer, message rendering, dark/light theme, responsive/mobile), running
  entirely on mock data with a `lib/api/*.ts` abstraction seam so Phase 2 can swap in real calls
  without touching components. See `web-phase1.md`.
- **Web Phase 2 — Auth, conversation/streaming API, file upload** (done): `lib/api/*` wired to the
  real backend (register/login, real SSE `POST /chat/stream`, `GET /conversations`, real
  `POST /documents` upload). See `web-phase2.md` for the real API contract found (narrower than
  the spec implied in places — no refresh token, no tool-call progress events) and what's
  deliberately deferred as a result. (Conversation rename/delete were added for real afterward —
  see the backend roadmap's 2026-08-30 addendum above; pin/archive are still deferred.)
- **Web Phase 3 — Knowledge/Agents/Tools/Settings pages** (done): real `/knowledge` (upload,
  search, delete), `/tools` (invoke the 3 real tools, real approve/reject on pending executions),
  `/agents` (run a real agent goal, render the real step trace, handle `waiting_approval` honestly
  since the backend never auto-resumes a paused run), and Settings' Usage + Account tabs wired to
  real data. See `web-phase3.md` for the real API contract found and what's deliberately deferred.
- **Web Phase 4 — Real AI backend integration hardening** (done, incrementally): all three things
  this was originally scoped for ended up done as part of earlier work rather than as one dedicated
  push — citations (Web Phase 2), tool-call/agent-run detail views (Web Phase 3), and the model
  selector wired to a real list (this backend roadmap's 2026-08-30 addendum above; today that list
  has exactly one real entry, honestly, not a fabricated multi-model catalog).
- **Web Phase 5 — Production hardening** (done): frontend CI (lint/build/`npm audit`, previously
  zero coverage), a real cross-tenant UI data-leak fix on logout→re-login (`chat-store.ts`'s
  `resetChatState()`), branded error boundaries (`error.tsx`/`global-error.tsx`, neither existed
  before), and conservative security headers. See `web-phase5.md` for what was audited, what was
  found, and what's deliberately still deferred (CSP, actual scaling work — no deploy target
  exists on either side yet).

## Odysseus feature-parity track — new, ongoing (started 2026-08-31)

A separate, open-ended multi-phase track (own numbering, not backend or web phases) working toward
matching [Odysseus](https://github.com/odysseus-dev/odysseus)'s feature set, one real capability at
a time. See [`odysseus-parity.md`](odysseus-parity.md) for the full ordered list and design detail.

- **Track Phase 1 — `web.search` tool** (done, fully verified with a real key): a real
  Tavily-backed web search Tool, registered like any other tool in the existing Tool System.
  Verified with genuine live search results (direct API, the Tools page UI, and a real Agent run
  that actually invoked it). Also caught and fixed a real pre-existing bug along the way — see
  `odysseus-parity.md`.
- **Track Phase 2 — Deep Research mode** (done): a frontend-only "Deep research" toggle on the
  Agents page that frames a plain question as a research-shaped goal for the existing, unmodified
  Agent loop + `web.search` — no backend change needed, as predicted when this track was planned.
  See `odysseus-parity.md` for what's verified vs. what still needs a real model provider to check
  (MockProvider's naive tool-matching can't demonstrate it picking `web.search` correctly).
- **Track Phase 3 — 2FA (TOTP)** (done): a real, self-contained TOTP implementation (`pyotp` on
  the backend, client-side QR rendering, no third-party service) — setup/confirm/disable endpoints,
  a login-flow change, migration `0007_totp` applied against the real running Postgres, and a real
  Settings → Security tab. Also fixed a real bug the full test suite run surfaced: the offline
  tests weren't isolated from the local `.env`'s real Tavily key. See `odysseus-parity.md`.
- **Phase 1 addendum — inline tool-calling in regular Chat** (done, 2026-08-31): `/chat` and
  `/chat/stream` never had any tool access before — only the separate Agents loop did. Chat now
  resolves up to `CHAT_MAX_TOOL_CALLS` (default 3) LOW-risk-only tool calls synchronously before
  its final answer, reusing the same message-augmentation pattern the Agent loop already uses, and
  finally feeds real data to the frontend's tool-call UI that had sat dormant since Web Phase 1.
  See `odysseus-parity.md`.
- Track Phases 4–11 (Notes/Tasks, Compare, Calendar, Documents editor, Cookbook, image tools,
  Email, MCP) are roadmap entries only — not yet designed, see `odysseus-parity.md`.

## Krixil learns — new track (started 2026-08-31)

A separate, ordered, incremental track (own numbering) giving Krixil actual learning capability,
beyond the frozen-weights local model from the Ollama integration above. See
[`learning-and-memory.md`](learning-and-memory.md) for the full design and a real,
load-bearing bug it caught live (FastAPI doesn't guarantee `BackgroundTasks` run after a
yield-dependency's own commit — caused a genuine `ForeignKeyViolationError` against real Postgres,
and separately corrupted the offline SQLite test suite via a shared-connection artifact).

- **Track Phase 1 — Long-term memory** (done): Krixil extracts and remembers durable facts about a
  user across all their conversations (not just within one), with a privacy toggle and a real
  Settings → Memory tab. Verified live: a fact stated in one conversation was correctly recalled in
  a brand-new, separate conversation with zero shared history.
- **Track Phase 2 — Auto-expanding knowledge base** (done): conversations become real, searchable
  RAG content via the existing hybrid-search pipeline, reusing Phase 1's own extraction call
  (extended to a two-category judgment) rather than a second LLM call per turn. Caught and fixed a
  second instance of Phase 1's background-task race live, this time silent rather than a thrown
  error — see `learning-and-memory.md`. Verified live end-to-end: a technical decision made in one
  conversation was correctly retrieved with real citations from a brand-new, separate conversation.
- **Track Phase 3 — Autonomous fine-tuning ("belajar mandiri")** (done): a new, separate,
  natively-Windows `training/` project (kept out of the `api` container — CUDA/GPU access a Linux
  container can't have) that periodically checks real conversation volume and, once there's
  enough (gated on Unsloth's own documented minimum, verified live), QLoRA fine-tunes Krixil's own
  model, evaluates the result against the existing evaluation harness, and only promotes it — as a
  new, additional, selectable model, never a silent swap — if it doesn't regress. Verified with a
  genuinely complete live run: 9 real, individually-diagnosed failures (a `trl` API version
  mismatch, three missing build tools, an Unsloth output-path quirk, a real change in Ollama's own
  `/api/create` contract) before a 10th attempt trained, converted, registered, evaluated, and
  promoted a real model — sent it a real chat message through Krixil's own `/chat` endpoint and
  got a coherent, correctly-cited response. See `learning-and-memory.md` for the full account.
  This closes out the "Krixil learns" track's original 3-phase scope.

## Coding agent — new (done, 2026-08-31)

The user asked directly for a real coding-agent capability — read/write files in a real project,
run commands, not just talk about code. Four new tools (`code.list_files`, `code.read_file`
LOW-risk; `code.write_file`, `code.run_command`, initially CRITICAL-risk/approval-gated like
`document.delete`, later changed to MEDIUM-risk/no-approval at the user's explicit, informed
request — see below) registered into the existing Tool System and reachable only through the
existing Agent loop. Command execution runs in a brand-new, privilege-separated `sandbox-runner`
service — the *only* component with Docker socket access in this stack, explicitly never the `api`
container — spinning up network-disabled, resource-limited, auto-removed containers per command. A
new `/code` page lets the user manage their own workspace files directly. Caught and fixed three
real bugs live: (1) Compose's actual project-prefixed volume name didn't match the literal name
first passed to `docker-py`, silently mounting an empty decoy volume; (2) approving an Agent's
paused tool call ran the tool but never updated the run's own displayed status/steps, since
nothing reconciled them after the fact; (3) a documented-but-easy-to-miss FastAPI behavior —
`Depends(..., yield ...)` cleanup (a session's own commit) runs *after* the response is already
sent — made `POST /agents/run` immediately followed by `GET /agents/{id}/status` 404 on the newer,
larger transaction, 100% reproducibly, fixed with an explicit commit before returning. See
[`coding-agent.md`](coding-agent.md) for the full security design and verification account.

Approval was then removed entirely from `code.write_file`/`code.run_command` (CRITICAL → MEDIUM
risk) at the user's explicit request, after being told plainly what it means, so a multi-step goal
doesn't stall on every write/command. A further request — real, unsandboxed access to an actual
folder on this machine (not just the isolated workspace) — added a second, separate native-Windows
service (`services/host-runner/`, same reasoning as `training/`: needs the real host, not a
container) and four `host.*` tools, with a root switcher on the `/code` page and a persistent
warning while that mode is active. See `coding-agent.md`'s "Real host-folder access" section for
the full trade-off and why a native service was needed instead of just loosening the Docker
sandbox. The Code page later gained real, per-(root, folder) session history in the sidebar
(mirroring Chat conversations, derived client-side from `AgentRun.goal` — no new backend model).

Chasing raw model "power" hit a real, checked ceiling (RTX 4060 Laptop, 8GB VRAM): a 2.78T-parameter
CPU-only model was ruled out live (needs 1.7TB disk against ~952GB total across both drives, and
~26.5s/token — verified against the project's own README, not assumed), a 32B model would need
partial CPU offload, and free-but-hosted options (Groq) or Kimi's API (no free tier, verified live)
trade away the self-hosted/private goal this whole track started from. Landed on switching the
default model from `qwen2.5:7b` to `llama3.1:8b` (a real, verified improvement in multi-step
tool-use attempts) and raising `agent_max_tool_calls` from 5 to 8 to match. Then, rather than keep
chasing model size, strengthened the coding agent itself: git/pytest/a compiler in the sandbox
image, a system prompt that actually asks for careful error-reading and test-iterate behavior, and
a real bug fix (`code.run_command`/`host.run_command`'s `timeout_seconds` upper bound was rejecting
requests instead of letting the existing clamp handle them). See `coding-agent.md`'s "Stronger
coding skills" section, including an honest, live-verified limit this did *not* fix: multi-step
goals can still make the small local model narrate a fabricated plan instead of calling real tools.

**Code page redesign — Claude Code look and feel (done, 2026-09-01).** User asked for the Code
page's UI and behavior to resemble Claude Code as closely as reasonable, explicitly keeping the
earlier no-approval decision for `code.*`/`host.*` tools unchanged. The functional centerpiece:
`POST /agents/run` no longer blocks for the whole loop — it now runs as a background task that
commits each step as it happens, so the frontend polls and renders the transcript live, step by
step, instead of showing nothing until one final result lands up to two minutes later. Frontend
tool-call/result rendering rewritten into compact, collapsible, monospace cards closer to Claude
Code's own tool feed. A real race this exposed (a goal submitted right after page load could get
silently wiped from view by a slower, already-in-flight history fetch) was caught live and fixed.
See `coding-agent.md`'s "Live, step-by-step transcript" section for the full account.

**Code page redesign, round two — a real "esc to interrupt," and closer visual fidelity (done,
2026-09-01).** First pass wasn't convincing enough — the page still read as a generic dashboard
around the transcript. Rewrote `StepView` again to literally match Claude Code's own `⏺ Tool(args)`
/ `⎿ result` glyphs (no cards, no per-tool icon set), dropped the chat-bubble goal line for a plain
`› instruction` prompt line, and rebuilt the composer as an actual prompt. Added a real "esc to
interrupt": `POST /agents/{id}/cancel` flips a still-running row's status, and `run_agent`'s loop
(`app/agents/runner.py`) now refreshes and checks that column every iteration, stopping between
steps if it's been cancelled — the same "finishes the current thing, then stops" shape Claude
Code's own interrupt has. See `coding-agent.md`'s "Round two" section for the full account
including the live verification (cancel genuinely reaches `step_count: 0` before any tool call).

**Removed the sandboxed "Workspace" mode from the Code page's UI entirely (done, 2026-09-01),** at
the user's explicit, confirmed-understood request — the reference product has no such toggle, just
one real environment plus a folder picker. Every new goal from this page now targets `host.*`
(real, unsandboxed) exclusively; `code.*`/`services/sandbox-runner` are untouched, just no longer
reachable from this page. The file-browser/upload/edit-file feature was Workspace-exclusive, so it
went with it — re-added afterward in a narrower, real form (see below). Also added, genuinely
functional not decorative: a real per-run model selector (`AgentRunRequest.model`, threaded
through `run_agent`'s `provider.tool_call(**model_kwargs)` as a `model=` override, same mechanism
Chat's own per-message model switching already used for Ollama's multiple local tags — live-
verified by explicitly requesting `qwen2.5:7b` and getting back "I am Qwen, developed by Alibaba
Cloud"), and a real file/photo attachment button (reuses the existing `host.write_file` upload
endpoint the removed file browser used — picks a file, uploads it into the folder that's open, and
tells the model to read it). The reference's other "+" menu items (slash commands, connectors,
plugins) are shown but disabled — Krixil has no system behind any of them, so they're visibly
inert rather than pretending to work.

**New: `cli/`, a terminal client for the same coding agent (done, 2026-09-01).** User asked for a
"powerful CLI like Blackbox and others." Not a second implementation of the agent loop — a Python
package (`pip install -e .`, real `krixil` command) that's purely a client of the exact same
`POST /agents/run`/`GET /agents/{id}/status`/`POST /agents/{id}/cancel` the web Code page uses,
rendering the identical `⏺`/`⎿` transcript in the terminal via `rich` (`cli/krixil_cli/render.py`
is a direct port of `step-view.tsx`'s logic). `krixil login` stores a session in
`~/.krixil/credentials.json`; `krixil` alone drops into an interactive loop scoped to whichever
real folder it's launched from (computed relative to a configured `HOST_ROOT`, the "operates where
you're standing" feel a real terminal coding agent has); `krixil run "<goal>"` is the scripted
one-shot form. `Ctrl+C` maps to the same cancel endpoint the web's "esc to interrupt" does. Live-
verified end to end from a real folder on the user's machine: a real `host.list_files` call
rendering correctly, a real file write+read round-trip, explicit model selection actually changing
which model answered — and, unprompted, the same known `llama3.1:8b` narration-instead-of-tool-
calling limitation from earlier in this track recurred on a two-step goal, confirming the CLI
faithfully reflects real backend behavior rather than masking it. 20 offline tests
(`pytest-httpx`-mocked, no running backend needed), ruff/mypy clean. See `cli/README.md`.

**`cli/` rebuilt in Node.js/TypeScript against a formal PRD (done, 2026-09-01).** User supplied a
full "Kirxil AI CLI" Product Requirements Document — an Autonomous Software Engineering Platform
vision (multi-agent orchestrator, Project Brain/AST/vector indexing, self-healing loop, browser/
vision agents, a 15+ service plugin ecosystem, swarm mode) — asking to update the CLI against it.
Told plainly this is a multi-year roadmap, not a session's work; user confirmed to proceed anyway
with the PRD's own recommended first phase (§50: CLI Runtime) and MVP scope (§37), and its
suggested CLI stack specifically (TypeScript/Node.js/Ink/Commander/Zod/execa) — replacing the
working Python CLI (kept at `cli-python/` for reference, not deleted). The PRD's *backend* stack
suggestion (Fastify/Postgres/BullMQ) and monorepo restructuring were deliberately not followed —
`services/ai-service` stays Python/FastAPI, already built and tested. Full PRD text kept at
`docs/architecture/kirxil-cli-prd.md`.
Three real bugs surfaced by the rewrite, none from the offline suite: a genuine backend step-
ordering bug in `list_agent_steps` (a tool_call and its observation share one step_number, and
without a secondary sort key Postgres doesn't guarantee which comes back first — the **web app had
this same latent bug**, just never hit it live; fixed with a `created_at` secondary sort plus a
new regression test asserting the actual step sequence), a real cross-drive path bug in
`dirFromCwd` (Windows `path.relative()` across drives doesn't start with `".."`, so the "outside
HOST_ROOT" check missed it — caught by a unit test), and a real error-handling bug in `kirxil
search` where a missing `ripgrep` binary silently printed "No matches." instead of the true
"not installed" state. See `coding-agent.md`'s "`cli/` rebuilt in Node.js/TypeScript against a
formal PRD" section for the full account, including the honest list of what the PRD describes that
isn't built (Project Brain, multi-agent orchestration, self-healing, visual/browser agents, plugin
ecosystem — all separate, much larger future phases).

**Permission Engine wired end-to-end for the CLI (done, 2026-09-01).** User asked to keep working
through the PRD. The PRD's §17 Permission Engine already existed in the backend (Phase 3, above)
and was already used by the web app, but nothing `host.*` ever reached HIGH/CRITICAL risk, so the
CLI never actually hit it. Bumped `host.run_command` to HIGH; fixed the real limitation that had
kept approval off `code.*`/`host.*` tools in the first place (see `coding-agent.md`'s "Approval
removed for `code.write_file`/`code.run_command`") — `run_agent()` could pause for approval but
never resume, so approving just ended the run early. `run_agent` now rebuilds its message history
from persisted steps and continues after approval (`AgentRun.model_id` persisted, migration
`0012_agent_run_model_id`, so the resumed run keeps the same model); `kirxil` prompts for a real
`y`/`n` in both `kirxil run` and the interactive REPL before a HIGH-risk command ever reaches
`host-runner`. Verified live against the real stack (real Ollama, real `host-runner`): a paused
run, a real approval that resumed the agent to a coherent second response, and a real rejection
that left `host-runner` untouched. Also fixed live: `buildGoal` telling the model to `cd` into a
directory it was already being passed as `host.run_command`'s own `directory` argument, which
sometimes double-applied the path and failed. Backend 158/158 tests, CLI 27/27 tests, both
lint/typecheck clean. See `coding-agent.md`'s "Permission Engine wired end-to-end for the CLI"
section and `cli/README.md`'s "Permission Engine" section.

**Checkpoint & Rollback for the CLI (done, 2026-09-01).** Continuing through the PRD in the same
session. `kirxil run`/the interactive REPL now auto-commit the current directory's real changes
(via `git`) right before a goal starts, and `kirxil undo`/`/undo` resets back to right before the
most recent one after showing the real diff and asking for a real `y`/`n` — `kirxil checkpoint
[message]` is the same snapshot on demand. Real `git`, not a custom undo log; scoped to git repos
only, and `undo` only ever targets a commit kirxil itself made. Along the way, found and fixed a
second real bug (unrelated to checkpoints): `kirxil search`'s existing "is `rg` installed" check
didn't actually work on Windows — execa/cross-spawn falls back to `cmd.exe` for an unresolvable
binary, producing the exact same `.failed`/exit-code-1 shape as ripgrep's own "zero matches" exit
code, so a genuine no-match search was misreported as "not installed." Fixed with an explicit
`where`/`which` probe before running the real search. CLI 32/32 tests (up from 27), tsc clean. See
`coding-agent.md`'s "Checkpoint & Rollback for the CLI" section and `cli/README.md`'s "Checkpoint
& Rollback" section.

**PRD §33 command surface + `git log`/`branch` + `doctor` (done, 2026-09-01).** Continuing through
the PRD. Added `kirxil ask/explain/analyze/generate/refactor/debug/test/review` — real goal
templates (`cli/src/verbs.ts`) on the same pipeline `run` already uses, so each one gets the live
transcript, the Permission Engine pause, and the pre-run checkpoint for free; `review` follows
§28's spec (reviews `git diff`, tags findings HIGH/MEDIUM/LOW). Added `kirxil git log`/`branch`
(§28) alongside the existing `diff`/`status`, and `kirxil doctor` (session/backend/git/rg/repo
health checks). Real bug found live testing `doctor`: it reported an expired session as "backend
not reachable," which is misleading — the backend was fine, only the token wasn't; fixed to
distinguish a 401 specifically. Verified live end to end (a throwaway registered account, since
this session's own saved token had coincidentally expired mid-session and its real password isn't
something to guess at — the existing credentials file was backed up first and restored
byte-for-byte after). CLI 40/40 tests (up from 32), tsc clean. See `coding-agent.md`'s "PRD §33's
command surface" section and `cli/README.md`'s "Command surface" section.

**`.kirxil.yml` project config + honest Model Router status (done, 2026-09-01).** Continuing
through the PRD. `.kirxil.yml` (`cli/src/projectConfig.ts`, discovered by walking up like `git`
finds `.git`) now provides `project.name`, `model.default`, and `agent.max_iterations` — a
deliberately small slice of §34's full YAML shape. `agent.max_iterations` reaches the backend for
real: a new `AgentRunRequest.max_steps` field, applied via `min(requested, settings.
agent_max_steps)` in `create_agent_run` so a project can only tighten its own step budget, never
raise it past the deployment's own ceiling. §30's Model Router (task-based auto-routing) is
explicitly *not* built — this deployment has exactly two real local models and no benchmark data
justifying a Reasoning/Coding/Fast/Vision/Local mapping between them, and inventing one would be a
fabricated capability; `model.default` is the honest version. `permissions:`/`sandbox:`/`memory:`
config and `agent.max_retries` are also deliberately not built, each for a specific reason
documented in `coding-agent.md` (`permissions:` especially — a client-supplied file changing what
the Permission Engine approves is a real security decision, not a side effect of "add a config
file"). Verified live against a second throwaway account (real `.kirxil.yml`, confirmed via a
direct backend query that the created run's `model_id`/`max_steps` genuinely came from the file,
and that `--model` still overrides it) — the user's own saved session was never touched. Backend
160/160 tests (up from 158), CLI 46/46 tests (up from 40), both lint/typecheck clean. See
`coding-agent.md`'s "`.kirxil.yml` project config" section and `cli/README.md`'s "Project config"
and "Model Router" sections.

**Anthropic (Claude) model provider (done, 2026-09-01).** User asked to move off the two local
Ollama models and use "Claude Code" and "Kimi K3" going forward. Built a real
`AnthropicModelProvider` (`app/ai/anthropic_provider.py`, `MODEL_PROVIDER=anthropic`) against
Anthropic's actual Messages API — genuinely not OpenAI-compatible (top-level `system` field,
`x-api-key` auth, `tool_use` content blocks, no `/embeddings` endpoint — delegates embeddings to
Ollama so RAG keeps working regardless of chat provider). Clarified "Claude Code" itself isn't an
API a backend connects to — it's Anthropic's own CLI product; the real equivalent is the Claude
API directly, which is what got built. For Kimi: Moonshot's models are documented as
OpenAI-API-compatible, so they likely need zero new code — just `OPENAI_BASE_URL` pointed at
Moonshot with a real key (documented in `.env.example`), not verified live since no Moonshot key
is available; "Kimi K3" specifically isn't a name this agent can confirm exists (K1/K1.5/K2 are
the known ones). Cannot obtain or fabricate a real API key for either provider — that requires the
account holder's own credential from console.anthropic.com or Moonshot's platform; the code is
real and ready, tested against 13 new tests (`test_anthropic_provider.py`, `test_ai_router.py`)
using mocked responses, not a live call to either vendor. Backend 173/173 tests (up from 160),
ruff/mypy clean. See `coding-agent.md`'s "A real Anthropic (Claude) model provider" section.

**`edit_file` + `search_files` — closing the PRD's MVP checklist (done, 2026-09-01).** User asked
to finish the PRD's own defined stages. §37's MVP scope named 10 items; 8 were already real, and
the remaining two — File edit (distinct from File write) and Code search (an agent-callable tool,
not just `kirxil search`'s local CLI passthrough) — were genuine gaps. Added `host.edit_file`/
`code.edit_file` (a Claude-Code-style unique `old_string`→`new_string` replacement, MEDIUM risk,
same tier as write) and `host.search_files`/`code.search_files` (real recursive regex search,
LOW risk, stdlib-only — deliberately not a shell-out to `rg`, after `kirxil search`'s own earlier
lesson about depending on an external binary's `PATH`). `host-runner` got a new `/search`
endpoint and, along with it, its **first test suite ever** (13 tests) — every tool it's carried
since the start of this track had zero coverage before this. `cli/src/goal.ts`/`render.ts`
updated so the CLI actually tells the model these tools exist and renders their results properly
(`Edit(path)`, `Search(pattern)`, match list). Verified live against the real stack: a real search
match with correct line number, a real precise file edit leaving the rest of the file untouched,
a full `kirxil run` showing the correct transcript end to end (another throwaway account used for
this, the real session backed up and restored again). Backend 183/183 tests (up from 173),
host-runner 13/13 (new), CLI 51/51 (up from 46), all lint/typecheck clean. This closes every item
on the PRD's own MVP checklist — see `coding-agent.md`'s "Closing the last two MVP gaps" section
and `kirxil-cli-prd.md`'s §37 status note.

**`delete_file` + `git blame` — the last two named gaps (done, 2026-09-01).** Continuing through
what the PRD itself flags as missing. Added `host.delete_file`/`code.delete_file` (HIGH risk,
approval-gated — a deliberately different, higher tier than write/edit, since a delete isn't one
more write away from being undone the way an overwrite is) and `kirxil git blame <file>` (the
fifth real local git passthrough command). Found and fixed a real test bug along the way: two
`test_agents.py` tests relied on `MockProvider`'s keyword-matching picking `document.delete` for
a "please delete document {id}" goal, but `code.delete_file`'s name now shares the word "delete"
and sorts first alphabetically — one test failed loudly, but a second
(`test_agent_stops_waiting_approval_for_critical_tool_...`) had been silently passing while
actually exercising the wrong tool (HIGH risk instead of CRITICAL), since its assertions weren't
specific enough to notice. Fixed by rewording the goals to anchor on the word "document" (unique
to that one tool) instead of the now-ambiguous "delete". Verified live: `host.delete_file` paused
for approval and only actually deleted the file after approving (confirmed both states directly);
`git blame` against a real tracked file in this repo's own history and a real untracked one (clear
error, not silent emptiness). Backend 187/187 tests (up from 183), CLI 53/53 (up from 51), both
lint/typecheck clean. See `coding-agent.md`'s "Two more real, small gaps closed" section.

**`kirxil plan` + `kirxil memory` (done, 2026-09-01).** Continuing through the PRD's named gaps.
`kirxil plan <goal>` (§19) is a 9th verb (`cli/src/verbs.ts`) — investigates, then answers as
"PLAN" + numbered steps + a rough estimate, explicitly makes no changes; stops there rather than
building a full plan→approve→execute state machine (an honest simplification of §19's implied
version, not the full thing passed off as complete). `kirxil memory list/add/forget/status/on/off`
(§33) needed zero new backend work — `app/memory/`'s long-term memory system already existed and
was already used by the web app, this just gives the terminal a real client of it
(`cli/src/api.ts` + a command group in `index.ts`; pulled a `requireApi()` helper out of six
copies of the same "resolve a client or bail" shape along the way). Verified live: memory's full
list/add/forget/status/on/off cycle against the real backend, watching each state change actually
take effect; `plan` producing a real goal matching the PRD's PLAN format and correctly triggering
the pipeline before the same already-documented `llama3.1:8b` multi-step-narration limitation
took over (unrelated to `plan` itself). CLI 59/59 tests (up from 53), tsc clean; backend
unchanged (no new endpoints needed). See `coding-agent.md`'s "Plan Mode and `memory`" section.

**`kirxil config` (done, 2026-09-01).** Last easy §33 gap closed. `.kirxil.yml` had real logic
(`cli/src/projectConfig.ts`) but no way to see what it actually resolved to short of reading the
raw file and re-deriving the fallback rules by hand. `kirxil config` shows which file was found
(if any) and each field's effective value with a plain-language fallback description when unset —
pure CLI-side, reusing `loadProjectConfig` as-is, no new backend surface. Verified live in both
states (no config file anywhere up the tree; a real file found correctly from two directories
below where it actually lives). CLI 61/61 tests (up from 59), tsc clean. This is the last of
§33's command-surface gaps closeable without new infrastructure — 14 of 22 real now. What's left
(`build`/`agent`/`swarm`/`deploy`/`monitor`/`project`/`plugin`) each need something this
deployment genuinely doesn't have. See `coding-agent.md`'s "`kirxil config`" section.

**`kirxil build` (done, 2026-09-01) — one more §33 item turned out closeable after all.** `build`
had looked like it needed real infrastructure like `deploy`/`monitor`/`agent`/`swarm`; on a
second look it's the same goal-template shape every verb already uses, just instructed to work
through all four of §20's phases (Plan/Implement/Test/Review) explicitly in one run, including
fixing and re-running a genuinely failing test rather than reporting it. Also determined §21 Auto
Mode needs no `--auto` flag at all — its own spec (autonomous, but HIGH-risk still needs approval,
nothing gets auto-blocked) already describes the CLI's real default behavior exactly; a flag would
toggle nothing real, so this was documented as closed by observation rather than shipped as a
cosmetic command. Verified live (a fourth throwaway account, real session backed up and restored
again): the goal text matched the four-phase template correctly and the run reached the backend
and completed, but made zero real tool calls this attempt (confirmed via the run's own API
record, not the printed transcript) — the same already-documented `llama3.1:8b` multi-step
narration limitation from earlier in this track, named plainly rather than glossed over. CLI
15/22 of §33 now real. 62/62 CLI tests (up from 61), tsc clean. See `coding-agent.md`'s
"`kirxil build` (§20) and an honest look at `--auto` (§21)" section.

**CLI visual overhaul — real subset of the "AI operating system" mockup (done, 2026-09-01).** User
shared a very detailed terminal-UI mockup styled after "Claude Code + Blackbox CLI" — boxed
panels, a multi-agent orchestrator tree, a swarm graph, a `kirxil brain` command with fabricated
indexing stats, security/deploy centers, "Always allow" permission memory, a self-healing loop
with attempt counters. About half described real UI polish over data Krixil already has; the
other half described capabilities that don't exist anywhere in this deployment. Built the real
half only, in the mockup's own visual language: a richer banner (real file/folder counts, real
online probe), real `-`/`+` diff rendering for edits (reusing the tool call's own real
`old_string`/`new_string`, one implementation shared by both the Ink REPL and `kirxil run`'s
plain-text output), a restyled permission panel showing the real risk level with a real typed-
`CONFIRM` variant for CRITICAL risk, derived step-state labels ("Running tests…"/"Editing…")
inferred from the real in-flight tool call, a real status bar (tool-call count, test-attempt
count, `git diff --stat`-derived change stats), two new commands (`kirxil init` scaffolds a real
`.kirxil.yml`; `kirxil sessions` lists real past runs via the existing `GET /agents` endpoint,
previously web-app-only), real test-attempt counting from the transcript's own `run_command`
calls, and a bordered `KIRXIL PLAN` panel for `kirxil plan` with a real `[Enter]` → `kirxil build`
handoff using the same goal (real chaining of two already-real commands, gated to actual
interactive terminals so piped/scripted use stays deterministic). Explicitly not built: the
multi-agent orchestrator tree/swarm mode (one real agent loop, nothing to render independently),
`kirxil brain`/Project Brain (§13, no indexer), `kirxil security` (no scanner),
`kirxil deploy`/`logs` (no deploy target), and "Always allow for project/session" (needs new
backend policy storage — a real security decision on its own). No backend changes. CLI 84/84
tests (up from 62), tsc clean. Verified live (a fresh throwaway account, real session backed up
and restored again): `kirxil init` → `kirxil config` round-trip; a real `kirxil run` edit showing
an actual `+1/-1` diff with the file's real content confirmed changed; `kirxil sessions` matching
`GET /agents` exactly; a real HIGH-risk `host.run_command` pause through the restyled panel,
resuming correctly after approval; a real `kirxil plan` goal rendering the model's actual plan
text in the bordered panel. The `[Enter]`-to-`build` handoff itself couldn't be driven through a
real keypress in this sandboxed environment (no TTY available to a non-interactively-launched
process here) — its own execution path reuses the already-verified run pipeline, but the actual
keypress-triggered path is unverified and worth a human check. See `coding-agent.md`'s "Visual
overhaul: the CLI's 'AI operating system' look, real subset only" section and `cli/README.md`.

## KIRXIL AI Stack v2 — a real, phased roadmap against the new PRD

The user shared a much larger follow-up PRD (2026-09-02): a full orchestration platform on top of
today's single-tenant, single-agent-loop backend — a KIRXIL Orchestrator, a multi-provider Model
Router, a Hermes Agent Engine adapter (confirmed real — NousResearch/hermes-agent, MIT, Feb 2026
— but its actual embeddable integration surface needs its own research spike before being
scoped), a Multi-Agent Swarm, a Project Brain (AST/symbol/vector indexing — pgvector is already
running in this deployment's own Postgres image, confirmed via exploration, making this
genuinely feasible without new infra), a 4-layer Memory system, an MCP Hub (currently zero MCP
code anywhere in the backend), a 4-tier Security layer with a real CRITICAL/BLOCK tier (today's
Permission Engine has all 4 `RiskLevel` values but no auto-block — everything either runs or
pauses for approval), a Self-Healing + Verification Engine (today's `kirxil build` "four phases"
are pure prompt text with zero enforcement, no retry/MAX_RETRIES concept anywhere), a Deployment
Engine (no real deploy target exists anywhere in this codebase — explicitly blocked until the
user names one), and a full `packages/*` monorepo restructure (explicitly sequenced **last**,
as its own dedicated migration pass, not bundled with feature work — a mechanical rename-and-move
across a working, tested system before any new functionality exists is pure risk for zero
functional value today). Full phase-by-phase sequencing and the "what's actually real today"
exploration findings live in `docs/architecture/kirxil-cli-prd.md`'s "KIRXIL AI Stack v2" status
note and the approved plan this was scoped from.

**Phase 1 — Model Router: real multi-provider support (done, 2026-09-02).** Added real
`openrouter` and `groq` providers — both confirmed (via their own docs) to be genuinely
OpenAI-compatible for chat *and* embeddings, so both reuse the existing `CloudModelProvider`
(`app/ai/cloud_provider.py`) with their own named config, the same way `ollama` already reuses it.
Added `huggingface` too — its router (`router.huggingface.co`) is OpenAI-compatible for chat only
(confirmed via HF's own docs, which explicitly say embeddings need a different endpoint shape), so
`CloudModelProvider` gained a new optional `embeddings_provider` delegation parameter (mirroring
`AnthropicModelProvider`'s existing pattern) rather than writing a bespoke fourth provider class —
a real simplification found during implementation, not scope creep. `app/ai/router.py` registers
all three with the same "requires an API key" guard the existing providers already have;
`app/ai/catalog.py` gained matching real catalog-description branches. **No API keys were
available for any of the three** — real code, tested against mocked HTTP responses only
(`tests/test_ai_router.py`, `tests/test_cloud_provider.py`), same honest caveat already
established for the existing `anthropic` provider. Backend 198/198 tests (up from 187),
ruff/mypy clean; `api` container rebuilt and confirmed to start cleanly with the new settings
present but unset (still defaulting to `MODEL_PROVIDER=ollama`, unaffected). See
`kirxil-cli-prd.md`'s §30 status note for the full provider list and the delegation-parameter
rationale.

**Phase 2 — Security: real CRITICAL/BLOCK tier (done, 2026-09-02).** Added a real, hard-coded
BLOCK outcome on top of the existing HIGH/MEDIUM approval flow — `app/tools/risk_rules.py`'s
`find_block_reason()`, a narrow, documented pattern list (recursive force-delete of `/`,
formatting/recursively deleting a whole Windows drive, writing/reformatting a raw disk device)
checked against `host.run_command`/`code.run_command`'s real command text via a new optional
`Tool.risk_classifier` hook (`app/tools/base.py`), wired into `request_tool_execution`
(`app/tools/service.py`'s new `_block()` helper) before the existing approval-pause logic ever
runs. A match becomes a genuinely new terminal `ToolExecution.status` — `"blocked"` — with its own
`tool.blocked` audit log entry, distinct from `"rejected"` (a human declined) since nothing was
ever offered for approval at all. No changes needed in `app/agents/runner.py`: its existing
"anything but completed/pending_approval is an error" branch already turns a blocked execution
into a real observation the model sees and reacts to. Deliberately narrow per the PRD's own
example split — `rm -rf /` blocks outright, but `DROP DATABASE production` stays at the existing
HIGH-risk approval pause rather than being escalated, since a legitimate migration really can
need that. CLI (`cli/src/api.ts`'s zod schema, `render.ts`'s observation summary — now labels a
blocked outcome "🚫 Blocked" instead of a generic "Error") and the web app (`ExecutionStatus`
type, the Tools page's status label and badge) both updated to recognize the new status.
Live-verified against the real running stack (a fresh throwaway account): `rm -rf /` and
`format C:` both returned `status: "blocked"` with the real reason and host-runner was never
called; an ordinary command still paused for approval unaffected. Backend 214/214 tests (up from
198), ruff/mypy clean; CLI 87/87 (up from 86), tsc clean; web app tsc clean. See
`kirxil-cli-prd.md`'s §17 status note.

**Phase 3 — Self-Healing + Verification: formalize `kirxil build` (done, 2026-09-02).** Two real,
independent mechanics, both replacing something that used to be pure prompt text with zero
enforcement.

*Self-Healing* — `app/agents/runner.py` now tracks real test-command attempts
(`host.run_command`/`code.run_command` whose command matches a real test-runner pattern) across a
whole run and stops it with an honest `final_response` once a real `AGENT_MAX_TEST_RETRIES`
(default 3) is hit and the latest attempt still failed — never silently retrying forever on the
generic step budget. The trickiest part: host.run_command is HIGH risk, so *every* real test
attempt genuinely pauses for approval first, and the approved tool's real execution/observation
happens in `app/tools/service.py`'s `_resolve_paused_agent_run`, not in the main loop — a first
version of this only checked the immediate-execution branch and silently never fired for
host.run_command at all (caught by the live-style integration test itself, not by inspection).
Fixed with a second check on the `resume=True` path, computing the attempt count from persisted
steps (correct across pause/resume boundaries) and checking whether the just-resolved step was a
failed test attempt. Verified via a real approve → resume cycle driven through 3 real
(mocked-host-runner) failing attempts, ending the run with the expected message and exactly 3
`host.run_command` steps recorded (`tests/test_agents.py`), plus 12 pure unit tests for the
detection helpers (`tests/test_runner_retry_detection.py`).

*Verification* — a new `verify:` list in `.kirxil.yml` (an ordered list of real shell commands),
run for real via a new `cli/src/verify.ts` (`execaCommand`, real subprocesses, stopping at the
first real non-zero exit) — deliberately *not* routed through `host.run_command`/the agent, since
these are commands the user themselves configured and already trusts, and gating each on a
HIGH-risk approval pause would be pure friction with no real safety benefit. A new
`kirxil verify` command runs it standalone; `kirxil build` automatically runs it afterward (both
the one-shot `runOnce.ts` path and the interactive REPL's plan → build handoff in `ui/App.tsx`) —
a real, deterministic check instead of trusting the model's own "Review" phase narration. Verified
live in a scratch directory: a 3-command pipeline with a failing middle step stopped there and
reported exit 1 with the real stderr, the remaining step never ran; an all-passing pipeline
reported exit 0; no `verify:` configured prints guidance instead of doing nothing silently.
Backend 227/227 tests (up from 214), ruff/mypy clean; CLI 94/94 (up from 87), tsc clean. See
`kirxil-cli-prd.md`'s §22 status note.

**Phase 4 — Multi-Agent Swarm: real parallel sub-agents (done, 2026-09-02).** A new `SwarmRun`
(`app/models/swarm_run.py`, `alembic/versions/0013_swarm_runs.py`) coordinates real decomposition
and real parallel execution — no Architect/Backend/Security "agent" implementations, just the
same one general agent loop this whole codebase already has, run several times concurrently with
different real goal text. `app/agents/swarm.py`: `decompose_goal()` makes one real model call
asking for a JSON array of 2–8 independent sub-tasks (defensive parsing, same code-fence-stripping
pattern `app/memory/long_term.py`'s extraction already uses) — fewer than 2 real sub-tasks is a
real, honest failure (`SwarmRun.status = "failed"`, a clear error message), never a fabricated
fallback or a silent single-member "swarm." Each real sub-task becomes an ordinary child
`AgentRun` (`swarm_run_id` FK), run concurrently via `asyncio.gather` — each in its own detached
`AsyncSession`, since SQLAlchemy's `AsyncSession` isn't safe for concurrent use from more than one
coroutine at once (same detached-session, rebuild-from-primitives shape
`run_agent_in_background` already established, reused here for N children instead of one).
One more real model call (`synthesize_results()`) combines every child's actual `final_response`
into a report, honestly naming any sub-task that failed. New endpoints under the existing
`/agents` router: `POST /agents/swarm`, `GET /agents/swarm`, `GET /agents/swarm/{id}/status`
(real per-child status nested in the response). New CLI command `kirxil swarm "<goal>"` polls and
prints real per-child status changes live, then the real synthesis. **Live-verified against the
real Ollama-backed stack** (not mocked): "make this application production ready" decomposed into
4 genuine sub-tasks, all ran in parallel with real tool calls, synthesis correctly and honestly
reported which sub-tasks actually failed; a second live run through the CLI itself decomposed
into 3 sub-tasks with an equally honest report. Backend 236/236 tests (up from 227) — including a
real approve-free integration test using a custom deterministic provider (MockProvider itself
never produces parseable JSON, which is itself the correct honest-failure path, covered by its
own test) — ruff/mypy clean. CLI 98/98 (up from 94), tsc clean. Not built: dependency-aware
sequencing between sub-tasks (every one runs independently and concurrently; no real "wait for
this other sub-task's result first" exists yet) — see `kirxil-cli-prd.md`'s §27 status note.

**Phase 5 — Project Brain: real symbol/vector index on the pgvector already running (done,
2026-09-02).** File Map, a real Symbol Index, and real Vector Index/Semantic Search — the pieces
of PRD §13 that don't need fabrication to be genuinely useful, scoped to `host.*`'s real
HOST_ROOT tree. New host-runner endpoint `GET /index-files` (`app/fs.py`'s `walk_indexable_files`,
same recursive-walk/ignored-dirs/binary-skip logic `search_files` already established, capped at
500 files) returns real `{path, content}` pairs. `app/brain/symbols.py`: real stdlib `ast`
parsing for Python (real line numbers via `node.lineno`/`end_lineno`); a real but deliberately
narrow regex heuristic for JS/TS/JSX/TSX (single-line declaration detection only — no fabricated
end-of-block claim, since that needs a real parser this pass doesn't add). `app/brain/service.py`
chunks real content by reusing `app/rag/chunker.py`'s `chunk_text` (the exact function document
upload already uses) and embeds it via whichever `ModelProvider` is active, storing it in a new
pgvector-backed `brain_chunks` table (HNSW index, `alembic/versions/0014_brain.py`) that a real
`<=>` cosine-distance query searches (`app/rag/search.py`'s own established pattern). New
endpoints `POST /brain/index`, `GET /brain/status`, `POST /brain/search`; a new agent-callable
`brain.search` tool (LOW risk) so the model itself can search by meaning mid-run, not just via
`host.search_files`' regex. New CLI commands `kirxil brain index`/`kirxil brain search "<query>"`.
Each new successful index run replaces the tenant's previous chunks outright — a fresh full
re-index, not incremental (no dependency tracking to know what changed).
**Live-verified against the real running stack**: indexed a real 3-file project (a Python file
with a function and a class, a JS file with a function and a class, a README) — found the real 6
symbols (4 Python + 2 JS, hand-verified exact), embedded 3 chunks; a real semantic search for "how
do we charge a customer's credit card" correctly ranked the file containing
`PaymentProcessor.charge()` first despite zero exact keyword overlap with the query, both via the
CLI and by calling the `brain.search` tool directly. Backend 249/249 tests (up from 236),
ruff/mypy clean — search itself has zero *offline* coverage by design, same real limitation
`app/rag/search.py`'s own vector/hybrid search already has (empirically confirmed pgvector's
`<=>` operator doesn't even compile against the SQLite test engine, not just "returns no rows").
Host-runner 22/22 (up from 13). CLI 102/102 (up from 98), tsc clean. Not built: Dependency Graph,
API Map, Database Map, real Git History (separate, much bigger subsystems, not attempted rather
than faked) — see `kirxil-cli-prd.md`'s §13 status note.

**Phase 6 — MCP Hub: real MCP client (done, 2026-09-02).** A real MCP (Model Context Protocol)
client (`app/mcp/client.py`) built on the official `mcp` Python SDK — deliberately pinned to
`1.9.4`, not latest, since the newest release forces an unrelated `pydantic` upgrade
(`2.10.2` → `2.13.5`) as a side effect; `1.9.4` is the newest version that resolves cleanly
against the existing pin. Stdio transport only this pass (real local subprocess servers; no
remote HTTP/SSE yet). New tenant-scoped `MCPServer` model (name/command/args/env, unique per
tenant+name) and `POST/GET/DELETE /mcp/servers` + `GET /mcp/servers/{id}/tools` endpoints
(`app/mcp/service.py`, `app/mcp/router.py`) — `env` values come back redacted (`***`) in every
response, never round-tripped in the clear. Three new agent tools (`app/tools/mcp_tools.py`):
`mcp.list_servers` (LOW), `mcp.list_tools` (LOW, connects live), `mcp.call_tool` (HIGH,
approval-gated exactly like `host.run_command`). New CLI commands `kirxil mcp add/list/remove/
tools`. New migration `alembic/versions/0015_mcp_servers.py`.
**Real bug found and fixed along the way**: `app/ai/mock_provider.py`'s naive tool-name word
matcher collided with the agent loop's own fixed boilerplate text (`"Tool result: {...}"`, sent
back as the next round's "user message" after every tool call) — since `mcp.call_tool` contains
the word "tool", every multi-step goal in the offline test suite started spuriously re-matching
it forever, exceeding `max_tool_calls` instead of completing. Fixed at the root with a
`_FRAMEWORK_BOILERPLATE_WORDS = {"tool", "result"}` exclusion in the matcher, rather than renaming
the tool (kept `mcp.call_tool` since it mirrors MCP's own `tools/call` spec vocabulary — the bug
was really "any future tool name containing 'tool' or 'result' would collide," not specific to
this one name).
**Live-verified against the real running stack**: built a real minimal Python MCP server
(`tests/fixtures/mcp_test_server.py`, official `FastMCP`, exposing `add(a,b)` and an
always-failing `fail()` tool), copied it into the running `api` container (excluded from the
image by `.dockerignore`'s `tests/` rule), registered it as a real MCP server via a throwaway
tenant, listed its tools live (`GET /mcp/servers/{id}/tools` returned real `add`/`fail` schemas),
then called `mcp.call_tool` end-to-end: a real HIGH-risk approval pause, and after approving,
a real result from the actual subprocess (`10 + 32 = 42`). Cleaned up afterward: throwaway server
config deleted, copied test file removed from the container, scratchpad session material deleted.
Backend 262/262 tests (up from 249), ruff/mypy clean. CLI 106/106 (up from 102), tsc clean.
**Not built, honestly**: remote MCP transports (HTTP/SSE) — stdio only; and the live `api`
container has no Node.js/npx installed, so the most common real-world MCP servers (npx-based,
e.g. `@modelcontextprotocol/server-filesystem`) can't actually be configured against this
deployment yet — only Python-based (or otherwise container-available) server commands work today.
Adding Node.js to the Dockerfile is a real, scoped follow-up, not attempted this pass. See
`kirxil-cli-prd.md`'s §16 status note.

**Phase 7 — Deployment Engine: still blocked.** No real deploy target (staging/production
environment, cloud account, anything) exists anywhere in this codebase. This phase does not start
until the user names a real one.

**Phase 8 — Repo restructure, adapted scope (done, 2026-09-02).** The PRD's literal `packages/*`
layout (§47) is per-concern **TypeScript** packages, designed for the PRD's own suggested
Node.js/Fastify backend (§46) — Krixil's real backend stayed Python/FastAPI instead (already a
documented deviation), so porting a fully built, 262-test backend into TypeScript packages for a
layout preference was rejected as a real project on its own, not attempted here. The user was
asked directly which real, adapted scope to pursue and chose the best-fit option: turn the two
Node.js projects that genuinely exist — `cli/` and `apps/web/` — into a real root npm workspace
(root `package.json`, one shared `package-lock.json`), instead of leaving them as two fully
separate npm installs.
**Real bug found and fixed by this pass's regression sweep, not shipped**: npm's default hoisting
moved `ink` (only `cli` depends on it) to the workspace root, where its bundled
`react-reconciler` resolved `apps/web`'s React 19 instead of the React 18 `cli` actually needs.
`ink`'s own `peerDependencies` range for React (`>=18.0.0`) is technically satisfied by 19, so
npm's own conflict detection never flagged it — the break only surfaced as a real runtime crash
(`Cannot read properties of undefined (reading 'ReactCurrentOwner')`) when re-running `cli`'s
Ink-render tests after the workspace conversion. Root-caused to dependency *placement*, not an
allowed version range, and fixed with `install-strategy=nested` in a new root `.npmrc` — keeps
each workspace's own dependency tree close to where it's used instead of npm's default blind
hoisting, at the cost of a larger `node_modules` (not committed; gitignored either way).
Also fixed along the way: CI (`.github/workflows/ci.yml`) never ran the CLI's own test/typecheck
suite at all — a real, pre-existing gap unrelated to this phase's own work, caught while updating
the frontend jobs' install step to run from the new workspace root. Added `test-cli` and
`security-cli` jobs; `lint-frontend`/`build-frontend`/`security-frontend` now `npm ci` from root
then run scoped via `npm run <script> -w apps/web` instead of a `working-directory: apps/web`
install.
**Verified**: CLI 106/106 tests (same suite as Phase 6, confirmed still passing after the fix),
tsc clean, `npm audit` 0 vulnerabilities. `apps/web` build/lint/`npm audit` all still pass
unchanged. Backend (`services/ai-service`) untouched — not part of this workspace, its own 262
tests unaffected. See `kirxil-cli-prd.md`'s §47 status note.
**Not done**: `services/ai-service`'s language/module layout, `services/host-runner`,
`services/sandbox-runner`, `training/` — none are Node.js projects a workspace applies to; the
PRD's literal `packages/*` TypeScript-package split remains a documented, deliberate deviation,
not attempted.

**Hermes Agent Engine — research spike, resolved as "do not integrate" (2026-09-02).** §8's
"Hermes Agent Engine adapter" needed a real look at its actual integration surface before being
scoped as a phase. Confirmed the real repo directly:
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — real, MIT-licensed,
active. But it's architecturally a standalone CLI/daemon (`hermes` commands, a `hermes gateway`
process for Telegram/Discord/Slack/WhatsApp/Signal), not a library: no pip-installable package
with a programmatic API, no documented REST/HTTP surface, and no one-shot non-interactive
invocation mode. It connects *to* MCP servers (an MCP client, the same role Krixil's own
`app/mcp/client.py` plays) but does not itself run as an MCP server another client could register
and call — so even Krixil's own real MCP Hub (Phase 6) isn't a usable integration path today. Its
own documented install method is `curl ... | bash` / `irm ... | iex` — this project has an
explicit prior lesson against running an installer script unread (see `learning-and-memory.md`'s
Unsloth-installer note), and did not make an exception here. **Conclusion: no real, safe
"AgentRuntime interface" surface exists to integrate against right now** — building one would mean
either shelling out to an undocumented, interactive-shaped CLI and hoping it behaves like a
one-shot tool, or waiting on Hermes itself to ship a library/API/MCP-server mode. Not attempted.
Revisit if that changes.

> **Correction (2026-09-03).** The "no documented REST/HTTP surface" finding above was outdated —
> the user supplied direct links into Hermes's real source
> (`gateway/platforms/api_server.py`/`api_server_runs.py`) proving it does ship a real, documented
> HTTP+SSE "Runs API" alongside ACP and a TUI-gateway JSON-RPC protocol. The *conclusion* that
> Hermes shouldn't be imported as a Python dependency still stands (now for a different, harder
> reason: its own exact-pinned `pydantic`/`httpx` versions genuinely conflict with this service's
> pins) — see the "Phase 11 — Hermes Runtime" entry below for what actually got built against the
> real HTTP+SSE surface once this was corrected.

**Phase 9 — MCP remote transport (sse/http) + Node.js in the api container (done, 2026-09-02).**
Closes Phase 6's own documented limitation: MCP was stdio-only, and the `api` container had no
Node.js, so the most common real-world MCP servers (npx-based, e.g.
`@modelcontextprotocol/server-filesystem`) couldn't actually be registered. `app/mcp/client.py`'s
single `_server_params` chokepoint became a `_connect` dispatcher across `stdio_client`,
`sse_client`, and `streamablehttp_client` (all three already present in the pinned `mcp==1.9.4`
SDK — verified directly against the installed source, no new dependency) — `list_server_tools`/
`call_server_tool`'s public signatures stayed unchanged, so `app/tools/mcp_tools.py`'s three agent
tools needed zero control-flow changes. New `MCPServer.transport`/`url`/`headers` columns
(migration `0016_mcp_remote_transport`, `command` now nullable), a first `model_validator` in this
codebase enforcing the right fields per transport in `MCPServerCreate`, and `headers` redacted in
every API response the same way `env` already is. **Real bug caught only by testing against a
genuine remote server, not by review**: `sse_client`/`streamablehttp_client` run their connection
inside an anyio `TaskGroup`, so a real connection failure (bad URL, unreachable host) surfaces as
an `ExceptionGroup` wrapping the real `httpx.HTTPError`, not the error itself — the existing
`except httpx.HTTPError` clause silently didn't catch it; fixed with a small recursive
`_find_http_error` unwrapper. `Dockerfile` gained `nodejs npm` in the existing single `apt-get
install` layer (Debian bookworm's packaged Node, confirmed `v20.19.2`/npm `9.2.0` via a real
`docker build` — comfortably above `npx`'s `>=18` floor). New tests follow this codebase's
established zero-SDK-mocking MCP philosophy: a new `tests/fixtures/mcp_test_server_remote.py`
(the same real `add`/`fail` server, run over real sse/streamable-http on an ephemeral port) plus
`tests/test_mcp_client_remote.py` — real subprocess, real protocol round-trip, including a real
unreachable-URL case that exercises the `ExceptionGroup` fix. **Documented, not silently accepted,
new trust-boundary note**: a tenant-supplied remote `url` means `GET /mcp/servers/{id}/tools` (not
approval-gated, only `mcp.call_tool` is) can make the `api` container issue a real outbound
request anywhere — accepted as within MCP registration's existing privileged trust boundary
(stdio already lets a tenant run an arbitrary local command), an egress allowlist is a real,
separate follow-up if this deployment ever needs to isolate tenants' network reach from each
other. **Live-verified against the real running stack, not just offline**: rebuilt the `api`
image, ran the real migration against the real Postgres, registered a real `npx -y
@modelcontextprotocol/server-filesystem` server against a real container-local directory, and
`GET /mcp/servers/{id}/tools` returned the package's real 14 advertised tools (`read_file`,
`write_file`, `search_files`, etc.) — genuine `npx` package fetch + real MCP stdio handshake
inside the container, the exact real-world case this phase existed to unblock. Backend 273/273
tests (up from 262), ruff/mypy clean. CLI (`api.ts`'s Zod schema, `kirxil mcp add --transport
sse/http --url --header`) updated to match; CLI 125/125, tsc clean.

**Phase 10 — Swarm dependency-aware sequencing (done, 2026-09-02).** Closes Phase 4's own
documented gap and PRD §27's own diagram (Backend/Frontend/Database → Testing → Security — a
genuine fan-out/join/sequential shape, not full independence). `decompose_goal`'s prompt and
`_parse_subtasks` now accept `[{"goal": ..., "depends_on": [0-based indices into this same
array]}, ...]` instead of a flat string array — array *position* is the index, deliberately not a
model-supplied id, removing a whole class of "model's id disagreed with its own position"
ambiguity. Same honest-failure discipline as before, extended: a self-reference, dangling
reference (including one only made dangling by `max_subtasks` truncation), or a cycle (detected
via stdlib `graphlib.TopologicalSorter(...).prepare()`) fails the *whole* decomposition, never
silently drops or reinterprets one bad edge. A new real edge table, `swarm_task_dependencies`
(migration `0017_swarm_task_dependencies`, own `tenant_id` for direct query scoping — same shape
as `AgentStep`, chosen over a JSON column since a dependency is genuinely many-to-many), replaces
the flat `asyncio.gather` fan-out with a `graphlib`-driven incremental scheduler (`_run_dag`) —
the same validated graph structure doubles as both validator and runtime scheduler, one
implementation not two; a child starts the instant its own prerequisites finish, not on a fixed
wave boundary. A dependent child's `AgentRun.goal` is rewritten once, in place, with its real
prerequisites' real completed output before it starts (new `AgentRun.original_goal` column
preserves the concise text for display) — chosen over threading a prompt-override parameter
through `run_agent`, since the HIGH-risk approval-resume path (`app/tools/service.py`) rebuilds
its first message from `agent_run.goal` with zero swarm awareness and would silently lose an
override. New `AgentRun.status` value `"queued"` (a blocked child no longer dishonestly claims
`"running"` while doing nothing) via a new `initial_status` param on `create_agent_run` (default
preserves every existing call site). **A prerequisite that failed doesn't block or skip its
dependent** — the dependent still runs, with an honest "did not complete successfully" note plus
the real failure text injected, extending `synthesize_results`'s existing "be honest about
failures" philosophy down into the hand-off itself rather than the orchestrator unilaterally
deciding the dependent is unsalvageable. New tests: 10 new `_parse_subtasks` cases (a diamond
graph matching the PRD's own diagram shape, self/dangling/cycle/truncation-invalidated rejections,
malformed items) plus two new full-HTTP-round-trip integration tests proving real data flow, not
just timing — one asserts a dependent child's own returned `goal` field literally contains its
prerequisites' real completed output text, the other exercises a real failed-prerequisite hand-off
end to end. Backend 281/281 tests (up from 273), ruff/mypy clean. CLI: new `SwarmChildOut`
schema (`depends_on`, `original_goal` — swarm-specific, not added to the general `AgentRunOut`),
`swarmChildStatusIcon` gained a `"queued"` icon, `SwarmTree.tsx` shows a queued child's real
concise `original_goal` plus a real "waiting on: ..." note resolved from its real sibling ids.
CLI 127/127 tests (up from 106), tsc clean. **Live-verified against the real Ollama-backed
stack**: applied the real migration against the real Postgres; one real run against a genuinely
ambiguous goal correctly hit the honest decomposition-failure path (the small local model's JSON
didn't form a valid graph — a known, already-documented model-quality limit, not a code bug); a
second real run against a simpler goal decomposed into 2 real independent sub-tasks
(`depends_on: []` on both, correctly round-tripped through the new API shape end to end) and
completed with a real synthesis. Proving the dependency-chain *happy path* live specifically
would need a local model reliably emitting the new structured JSON shape — not attempted further
given this project's own prior, repeated findings about small local models and structured
multi-step output; the deterministic-provider integration tests above already prove that exact
mechanism directly and repeatably. See `kirxil-cli-prd.md`'s §27 status note.

**Phase 11 — Hermes Runtime: a real `AgentRuntime` alternative over Hermes's real HTTP+SSE API
(done, 2026-09-03).** The earlier Hermes research spike (this file's "Hermes Agent Engine —
research spike" entry above) concluded there was no safe integration surface — that conclusion
was outdated, corrected after the user supplied direct links into Hermes's real source proving it
ships a documented "Runs API" (`POST /v1/runs`, `GET /v1/runs/{id}/events` SSE, `.../approval`,
`.../stop`). Still never imported as a Python dependency — Hermes exact-pins
`pydantic==2.13.4`/`httpx==0.28.1`, directly incompatible with this service's own pins — so it
runs as its own separate service, reached over that real HTTP API, matching the existing
`sandbox-runner`/`host-runner`/`training` pattern. New `AgentRun.runtime`/`external_run_id`
columns (migration `0018_agent_run_runtime`), a new `app/agents/hermes_client.py` (real HTTP+SSE
client, verified endpoint shapes) and `app/agents/hermes_runtime.py` (translates Hermes's real
events into the exact same `AgentStep` rows the native loop writes — zero CLI rendering changes).
**The confirmed, non-negotiable requirement**: Krixil's own Permission Engine stays the single
source of truth for every tool approval, even for a Hermes-originated run. A 3-tier policy
(`classify_hermes_approval`) — a real match against `app/tools/risk_rules.py`'s existing
destructive-command patterns or an opaque request (no tool name at all) auto-denies without ever
reaching a human; every other real, inspectable request becomes a genuine
`ToolExecution(tool_name="hermes.<tool>", risk_level="high")` row resolved through the exact same,
unmodified `/tools/executions/{id}/approve`/`reject` endpoints every native HIGH-risk tool call
already uses — proven end to end in tests, not just asserted. `app/tools/service.py`'s
`approve_execution`/`reject_execution` each gained one branch (a Hermes-bridged execution has no
local `tool.handler` to run — approving it tells Hermes `"once"` directly instead). CLI:
`--runtime <native|hermes>` on `run`/every verb/the bare REPL, `.kirxil.yml`'s `agent.runtime`
default, same precedence shape as `--model`/`model.default`. Tests follow this codebase's
established "real fixture server, not a mocked SDK" discipline —
`tests/fixtures/hermes_fixture_server.py` is a real, scriptable HTTP+SSE server implementing
Hermes's real documented shape, exercised by `tests/test_hermes_client.py` (8 tests) and
`tests/test_hermes_runtime.py` (6 tests, including a full approval round trip through the real
unmodified approve endpoint). Backend 295/295 tests (up from 281), ruff/mypy clean. CLI 130/130
(up from 106), tsc clean. **Not done, explicitly**: actually installing/running a real Hermes
instance (the user's own call, not attempted autonomously — same "don't pipe an installer to a
shell unread" caution as before), swarm-per-child runtime selection, ACP, the TUI-gateway JSON-RPC
protocol. A real live-Hermes smoke test is a manual follow-up once the user has one running with a
real `API_SERVER_KEY`. See [`hermes-runtime.md`](hermes-runtime.md) for the full design account.
