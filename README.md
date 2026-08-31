# Krixil AI

Self-hosted, multi-tenant AI platform, built in disciplined phases — see
[`docs/architecture/roadmap.md`](docs/architecture/roadmap.md) for what each phase added and
[`docs/architecture/`](docs/architecture/) for the design notes and trade-offs behind each one.

**Status: Phases 0–5 complete.** One FastAPI service (`services/ai-service`) with: auth + tenant
isolation, a model-provider abstraction (mock provider by default, no API key needed, or a real
OpenAI-compatible provider), streaming chat with Redis short-term memory, RAG (document upload →
pgvector + full-text hybrid search → cited chat answers), a permission/risk-gated Tool System with
human approval for risky actions, an agent loop that calls those tools autonomously within
budgets, an AI evaluation harness, and Prometheus/Grafana/OpenTelemetry observability.

## Prerequisites

- **Python 3.11+** — https://www.python.org/downloads/
- **Docker Desktop** — https://www.docker.com/products/docker-desktop/ (includes Compose; enable
  the WSL2 backend on Windows)

Verify: `python --version`, `docker --version`, `docker compose version`.

## Quickstart (Docker — recommended)

```powershell
cd D:\Krixil
Copy-Item services\ai-service\.env.example services\ai-service\.env
# edit services\ai-service\.env and set a real JWT_SECRET:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

# --env-file is required (not optional): it's the file Postgres/MinIO bootstrap their
# credentials from, and it must be the same file the api container reads — see the note
# at the top of infrastructure/compose/docker-compose.yml.
$envFile = "--env-file", "services\ai-service\.env"
docker compose $envFile -f infrastructure\compose\docker-compose.yml up --build -d
docker compose $envFile -f infrastructure\compose\docker-compose.yml exec api alembic upgrade head
```

| Service | URL |
|---|---|
| API + interactive docs | http://localhost:8000/docs |
| Metrics (Prometheus format) | http://localhost:8000/metrics |
| Sandbox runner (coding-agent command execution — see `docs/architecture/coding-agent.md`) | http://localhost:8001/health |
| Prometheus | http://localhost:9090 |
| Grafana ("Krixil AI - Overview" dashboard, anonymous admin — **local dev only**) | http://localhost:3001 |
| Jaeger (traces) | http://localhost:16686 |
| MinIO console | http://localhost:9001 |

```powershell
curl http://localhost:8000/api/v1/health

# register a tenant + owner user
curl -X POST http://localhost:8000/api/v1/auth/register `
  -H "Content-Type: application/json" `
  -d '{"tenant_name":"Acme Inc","email":"owner@acme.dev","password":"correct-horse-battery"}'

# use the returned access_token
curl -X POST http://localhost:8000/api/v1/chat `
  -H "Authorization: Bearer <access_token>" `
  -H "Content-Type: application/json" `
  -d '{"message":"hello"}'
```

Stop the stack: `docker compose -f infrastructure\compose\docker-compose.yml down` (add `-v` to
also drop the data volumes).

## Local development (without Docker for the API)

```powershell
cd services\ai-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# Postgres/Redis/MinIO still need to run somewhere:
docker compose --env-file .env -f ..\..\infrastructure\compose\docker-compose.yml up -d postgres redis minio

alembic upgrade head
uvicorn app.main:app --reload
```

## Tests, lint, type check

The test suite runs fully offline (SQLite in-memory + fakeredis + respx) — no Docker required.
A handful of RAG/evaluation cases are Postgres-specific (pgvector, full-text search) and are
verified live instead (see `docs/architecture/phase2.md`), not in this suite.

```powershell
cd services\ai-service
pytest -v
ruff format --check .
ruff check .
mypy app/
```

## AI evaluation harness

```powershell
# with the Docker stack up and migrated:
docker compose -f infrastructure\compose\docker-compose.yml exec api python scripts/run_evaluations.py
```

Runs a fixed suite of checkable cases (RAG retrieval, citation quality, tool-call selection,
latency, token budget) against a dedicated internal tenant, records the run, and compares it
against the previous baseline. Exits non-zero on any failure or regression — this is what gates
`.github/workflows/ci.yml`'s `build-and-verify` job. See `docs/architecture/phase5.md`.

## CI/CD

`.github/workflows/ci.yml` runs on every push/PR to `main`: lint, type check, unit tests, and a
security scan (dependency + static analysis) run in parallel, then a build-and-verify job brings
up the real Docker stack, migrates, runs the evaluation harness, and smoke-tests register→chat.
Deploying to staging/production isn't automated yet — there's no target host to deploy to; see
`docs/architecture/phase5.md`.

## Project layout

```
services/ai-service/     the FastAPI application
services/sandbox-runner/ isolated command execution for the coding agent (the only service with Docker socket access)
services/host-runner/    real, unsandboxed access to a folder on this machine for the coding agent — native Windows, not Docker; see its README before running it
infrastructure/compose/   Docker Compose stack (api, postgres, redis, minio, prometheus, grafana, jaeger, sandbox-runner)
docs/architecture/        design notes, trade-offs, and the roadmap for each phase
.github/workflows/        CI/CD pipeline
```

Other directories described in the long-term architecture (`apps/`, `packages/`, `models/`,
`training/`, Kubernetes/Terraform under `infrastructure/`) are intentionally not created yet —
they get scaffolded when a phase actually needs them, per the project's own "don't over-engineer
early" rule.
