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

This closes out the original backend roadmap. **Addendum (2026-08-30)**: conversation rename
(`PATCH /conversations/{id}`) and delete (`DELETE /conversations/{id}`) added, plus a related
tenant+user-scoping tightening on `GET /conversations/{id}` — see `phase1.md`'s addendum section.
Later, not yet scheduled: fine-tuning (LoRA/QLoRA) pipeline, self-hosted inference via vLLM,
Kubernetes migration, staging/production hosts (needed before Phase 5's deploy automation can be
finished), a model-listing endpoint + per-request model selection, a second role + requester/
approver separation for tool approvals (needs an invite/add-user endpoint first — see phase3.md),
agent-run resume-after-approval (see phase4.md), conversation pin/archive (needs a schema
migration).

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
- **Web Phase 4 — Real AI backend integration hardening** (not started): memory/RAG/model-router
  behavior surfaced properly in the UI (citations, tool-call detail views, model selector wired to
  real model list).
- **Web Phase 5 — Production hardening** (not started): monitoring, security, multi-tenant UI
  concerns, scaling — mirrors the backend's own Phase 5 concerns on the frontend side.
