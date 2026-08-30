# Krixil AI

Self-hosted, multi-tenant AI platform. Built in phases — see [`docs/architecture/phase0.md`](docs/architecture/phase0.md)
for the current phase's architecture and [`docs/architecture/roadmap.md`](docs/architecture/roadmap.md) for what comes next.

**Status: Phase 0 — Foundation.** One FastAPI service (`services/ai-service`) with auth, tenant isolation,
a model-provider abstraction (mock provider only, no API key needed), and a streaming chat endpoint backed
by Postgres + Redis.

## Prerequisites

You need these installed locally (neither was found on this machine — install before running):

- **Python 3.11+** — https://www.python.org/downloads/ (check "Add to PATH" during install on Windows)
- **Docker Desktop** — https://www.docker.com/products/docker-desktop/ (includes Compose; enable the WSL2 backend on Windows)

Verify:

```powershell
python --version
docker --version
docker compose version
```

## Quickstart (Docker — recommended)

```powershell
cd D:\Krixil
Copy-Item services\ai-service\.env.example services\ai-service\.env
# edit services\ai-service\.env and set a real JWT_SECRET (and Postgres/MinIO passwords if you want)

# --env-file is required (not optional): it's the file Postgres/MinIO bootstrap their
# credentials from, and it must be the same file the api container reads — see the note
# at the top of infrastructure/compose/docker-compose.yml.
$envFile = "--env-file", "services\ai-service\.env"
docker compose $envFile -f infrastructure\compose\docker-compose.yml up --build -d
docker compose $envFile -f infrastructure\compose\docker-compose.yml exec api alembic upgrade head
```

API is now at http://localhost:8000 — interactive docs at http://localhost:8000/docs.

```powershell
# health check
curl http://localhost:8000/api/v1/health

# register a tenant + owner user
curl -X POST http://localhost:8000/api/v1/auth/register `
  -H "Content-Type: application/json" `
  -d '{"tenant_name":"Acme Inc","email":"owner@acme.test","password":"correct-horse-battery"}'

# use the returned access_token
curl -X POST http://localhost:8000/api/v1/chat `
  -H "Authorization: Bearer <access_token>" `
  -H "Content-Type: application/json" `
  -d '{"message":"hello"}'
```

Stop the stack: `docker compose -f infrastructure\compose\docker-compose.yml down` (add `-v` to also drop the data volumes).

## Local development (without Docker for the API)

```powershell
cd services\ai-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# Postgres + Redis still need to run somewhere — e.g. just the infra services from compose:
docker compose --env-file .env -f ..\..\infrastructure\compose\docker-compose.yml up -d postgres redis minio

alembic upgrade head
uvicorn app.main:app --reload
```

## Tests

Tests run fully offline (SQLite in-memory + fakeredis) — no Docker or Postgres required:

```powershell
cd services\ai-service
pytest -v
```

## Project layout

See [`docs/architecture/phase0.md`](docs/architecture/phase0.md) for the full breakdown. Top level:

```
services/ai-service/   the FastAPI application (Phase 0)
infrastructure/compose/ Docker Compose stack for local dev
docs/architecture/      architecture notes and roadmap
```

Other directories described in the long-term architecture (`apps/`, `packages/`, `models/`, `training/`,
Kubernetes/Terraform under `infrastructure/`) are intentionally not created yet — they get scaffolded when
the phase that needs them starts, per the project's own "don't over-engineer early" rule.
