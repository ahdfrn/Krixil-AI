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
