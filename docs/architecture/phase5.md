# Phase 5 — Evaluation, observability, hardening

## Scope decisions

Two more instances of the pattern from Phases 3–4: the spec's staging/production deploy stages
have no real target infrastructure to deploy to yet, so they're documented as manual follow-ups
rather than faked automation (see CI/CD below). Everything else — observability and the
evaluation harness — is real, wired up, and verified live, the same bar every other phase met.

## Observability

- **Metrics** (`GET /metrics`, Prometheus format): `prometheus-fastapi-instrumentator` gives
  `http_requests_total` and `http_request_duration_seconds` (by handler/method/status) for free.
  Custom histograms/counters in `app/observability/metrics.py` cover what it can't:
  `krixil_model_request_duration_seconds` (by provider/operation), `krixil_token_usage_total` (by
  model/token_type), `krixil_tool_execution_duration_seconds` (by tool/status),
  `krixil_rag_search_duration_seconds`, `krixil_agent_steps_total` (by step_type), and
  `krixil_short_term_memory_cache_total` (hit/miss — this is the "cache_hit_rate" metric the spec
  names). GPU metrics from the spec's list aren't emitted — there's no GPU inference yet
  (self-hosted vLLM is a later, unscheduled phase); adding them then is a natural extension of
  this same file.
- **Tracing**: OpenTelemetry, FastAPI + httpx auto-instrumented, plus explicit spans at
  `rag.retrieval` and `tool.execute` (with `tool.name`/`tool.risk_level` attributes) so a trace
  actually shows the spec's Request → Retrieval → Model → Tool → Response shape, not just one
  flat request span. Exports via OTLP/HTTP to Jaeger by default. `OTEL_ENABLED` is opt-out, not
  opt-in — verified that leaving it on with no collector reachable degrades to a harmless
  background export failure, never a request-path error (except see the compatibility bug below).
- **Logging**: unchanged from Phase 0 — already structured JSON with `request_id` correlation.

**Local stack additions**: Prometheus (scrapes `api:8000/metrics` every 15s), Grafana (a
provisioned "Krixil AI - Overview" dashboard with 9 panels, anonymous admin access —
**local dev only**, not for anything internet-facing), Jaeger all-in-one (UI on :16686, OTLP
receiver on :4318).

## Evaluation harness

Same shape as Phase 3/4's tool/agent registries: `app/evaluation/base.py` (`EvalCase`,
`register_case`), one module per category, `app/evaluation/runner.py` executes them, records
`evaluation_runs`/`evaluation_results`, and flags `regression` when this run's pass count drops
below the most recent prior completed run for that tenant — matching the spec's
New Change → Run Evaluation → Compare Baseline → Pass Threshold? flow exactly.

Real cases, chosen because they're objectively checkable without needing a real LLM as judge
(spec categories like "Reasoning" or "Business Analysis" quality would need exactly that, which
isn't available without a real model API key — deferred honestly rather than faked with a
rubber-stamp check): `rag.known_document_retrieval`, `citation_quality.chat_cites_relevant_document`,
`tool_calling.selects_usage_summary_tool`, `latency.generate_under_threshold`,
`cost.generate_within_token_budget`.

Run via `python scripts/run_evaluations.py` against a real Postgres/Redis/MinIO (creates/reuses a
dedicated `krixil-evaluation` tenant); exits 1 on any failure or regression, meant to gate the
CI/CD pipeline's deploy step. **Not exposed as a tenant-facing API** — this is an ops/CI concern
that runs against a dedicated internal tenant, not a per-tenant self-service feature.

`run_evaluation_suite()` takes an optional `cases=` override specifically so tests can pass a
small self-contained list instead of the global registry — importing anything from
`app.evaluation.base` unavoidably runs `app/evaluation/__init__.py` (which registers the real
cases, several needing Postgres), so without this the offline SQLite test suite would silently
pick up cases it can't actually run. Found by running the tests, not by inspection.

## CI/CD

`.github/workflows/ci.yml`: `lint` (ruff format + check) → `typecheck` (mypy) → `test` (offline
pytest) → `security` (pip-audit + bandit) run in parallel, then `build-and-verify` (gated on all
four passing) builds the Docker image, brings up the real stack, runs migrations, runs the
evaluation harness, and smoke-tests register→chat — the exact sequence this phase was verified
with manually, now automated. **Deploy Staging / Production are deliberately not implemented** —
there's no staging or production host to deploy to; wiring that in later is a config change
(target + registry secrets + a deploy step), not a design change, since everything up to "the
image builds and the whole stack works end-to-end" is already proven on every push.

## Hardening done along the way

- **Dependency vulnerabilities**: `pip-audit` found 59 known CVEs across 5 packages (versions had
  drifted since they were first pinned in earlier phases and were never actually scanned before
  now). Fixed 58 by bumping `python-jose`, `python-multipart`, `pypdf`, and `fastapi`/`starlette`
  to current versions. The 1 remaining (`ecdsa`, a transitive dependency of `python-jose`) is the
  well-known "Minerva timing attack" advisory the `python-ecdsa` maintainers have declared out of
  scope — it only affects ECDSA-family JWT algorithms, and this app only ever configures
  `JWT_ALGORITHM=HS256` (HMAC, no ECDSA). Documented and explicitly accepted in the CI security
  job, not silently suppressed.
- **A real compatibility bug the version bump itself caused**: jumping `starlette` to 1.x broke
  `opentelemetry-instrumentation-fastapi==0.49b2`'s route-name extraction (`AttributeError:
  '_IncludedRouter' object has no attribute 'path'`), turning *every* HTTP request into a 500.
  Only caught because the bumped stack was rebuilt and hit live, not from the offline suite (which
  doesn't exercise the OTel FastAPI middleware's route-inspection code path the same way a real
  ASGI request does). Fixed by bumping the OpenTelemetry instrumentation packages to a mutually
  compatible set (`opentelemetry-api`/`sdk` 1.44.0, instrumentation packages 0.65b0). This is
  exactly the kind of thing "the offline suite is green" would never have caught — see the
  standing project-memory note about always verifying live.
- **Lint/type debt paid down**: `ruff format` + `ruff check --fix` cleared ~130 accumulated
  formatting/style issues (the `pyproject.toml` line-length rule existed since Phase 0 but was
  never actually enforced until now); 4 genuine `raise ... from` fixes (preserves the original
  exception context instead of discarding it); `mypy` added fresh and brought to a clean baseline
  (one real naming collision fixed — `main.py` did `import app.tools` then later reassigned `app`
  to the FastAPI instance, shadowing the package reference; harmless at runtime since nothing
  after that line touched `app.tools` again, but exactly the kind of latent footgun worth fixing
  properly rather than leaving for a future edit to trip over).

## Verified

Offline suite: 79/79 tests pass (evaluation harness mechanics fully covered offline via injected
fake cases; the 5 real cases are Postgres-dependent, verified live). `ruff format --check`, `ruff
check`, and `mypy app/` all clean. `pip-audit` clean except the one documented, accepted exception.
`bandit -r app/ scripts/ -ll` clean (4 low-severity/false-positive findings below that threshold —
a non-cryptographic PRNG used for deterministic fake embeddings, and metric-label strings bandit's
keyword heuristic mistook for hardcoded passwords). Live in Docker: full CI job sequence manually
replayed end-to-end (build → up → migrate → evaluate → smoke test) on a clean volume, including
catching and fixing the starlette/OTel incompatibility above. Prometheus confirmed scraping
(`up`), Grafana dashboard confirmed loaded with working panel queries against real metric names,
Jaeger confirmed receiving traces with the custom `tool.execute` span nested correctly under its
request span.
