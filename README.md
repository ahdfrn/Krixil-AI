# Krixil AI

Self-hosted, multi-tenant AI platform — chat, RAG, tools, autonomous agents, a coding agent with
real host-machine access, long-term memory, an auto-expanding knowledge base, and autonomous
fine-tuning. Built in disciplined phases — see [`docs/architecture/roadmap.md`](docs/architecture/roadmap.md)
for what each phase added and [`docs/architecture/`](docs/architecture/) for the design notes and
trade-offs behind each one.

## Architecture at a glance

| Component | What it is | Runs via | Required? |
|---|---|---|---|
| `services/ai-service` | The FastAPI backend — auth, chat, RAG, tools, agents, memory, fine-tuning API | Docker Compose | Yes |
| `services/sandbox-runner` | Isolated, network-disabled command execution for the coding agent | Docker Compose | Yes |
| `apps/web` | The Next.js web UI | `npm run dev` (native) | Yes, for the UI |
| Postgres, Redis, MinIO | Database, cache, object storage | Docker Compose | Yes |
| Prometheus, Grafana, Jaeger | Metrics/dashboards/traces | Docker Compose | No — observability only |
| Ollama | Local model runtime (chat + embeddings) | Native, installed separately | No — a `mock` provider needs no setup, but gives canned answers |
| `services/host-runner` | Real, unsandboxed access to a folder on this machine — what the coding agent (web and CLI both) actually runs against | Native (`uvicorn`) | Yes, for the coding agent |
| `cli/` | `kirxil` — a terminal client for the same coding agent the web app's Code page uses | Native (Node.js, `npm install && npm run build`) | No — optional, alternative to the web UI |
| `training/` | Autonomous fine-tuning scheduler | Native (`python`) | No — optional |

Everything in the "Docker Compose" row comes up together with one command. Everything marked
"Native" runs directly on Windows (not in a container) because it needs something Docker can't
give it: `apps/web` needs a fast dev-reload loop, Ollama/`training/` need real GPU access, and
`host-runner` needs to touch real files on your machine, not a sandboxed volume.

`cli/` and `apps/web/` are a real root npm workspace (root [`package.json`](package.json)) — one
`npm install` at the repo root installs both, or run it inside either directory as shown below,
which works the same way. `services/ai-service` (the backend) stays a separate Python project,
deliberately not folded into this workspace — see `docs/architecture/kirxil-cli-prd.md`'s §46/§47
status notes for why.

## Prerequisites

- **Python 3.11+** — https://www.python.org/downloads/
- **Docker Desktop** — https://www.docker.com/products/docker-desktop/ (includes Compose; enable
  the WSL2 backend on Windows)
- **Node.js 20+** — https://nodejs.org/ (for `apps/web`)
- **Ollama** — https://ollama.com/download — optional, only if you want real model responses
  instead of the canned `mock` provider

Verify: `python --version`, `docker --version`, `docker compose version`, `node --version`.

## First-time setup

### 1. Configure the backend

```powershell
cd D:\Krixil
Copy-Item services\ai-service\.env.example services\ai-service\.env
```

Edit `services\ai-service\.env`:
- Set a real `JWT_SECRET`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- Decide how the AI answers — see [Choosing a model provider](#choosing-a-model-provider) below.
  The file defaults to `MODEL_PROVIDER=mock` (zero setup, canned responses) — switch it to
  `ollama` once Ollama is installed if you want real answers.

### 2. Build the coding-agent's sandbox image (one-time)

```powershell
docker compose --env-file services\ai-service\.env -f infrastructure\compose\docker-compose.yml `
  --profile build-only build sandbox-runner-image
```

This builds the image the coding agent's ephemeral run containers actually use (`git`, `pytest`,
build tools pre-installed). It's a separate, on-demand build — not a long-running service — so it
isn't part of `docker compose up`. Re-run this any time
`services/sandbox-runner/runner-image/Dockerfile` changes.

### 3. Start the Docker stack

```powershell
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
| Sandbox runner health | http://localhost:8001/health |
| Prometheus | http://localhost:9090 |
| Grafana ("Krixil AI - Overview" dashboard, anonymous admin — **local dev only**) | http://localhost:3001 |
| Jaeger (traces) | http://localhost:16686 |
| MinIO console | http://localhost:9001 |

```powershell
curl http://localhost:8000/api/v1/health
```

### 4. Start the web app

```powershell
cd apps\web
npm install
Copy-Item .env.example .env.local   # defaults to http://localhost:8000/api/v1 — correct as-is
npm run dev
```

Open **http://localhost:3000**, register a tenant (this creates your account — the register form
is the front door, there's no separate seed step), and start chatting.

## Choosing a model provider

Set `MODEL_PROVIDER` in `services\ai-service\.env`:

- **`mock`** (default) — no setup, no API key, deterministic canned responses. Good for verifying
  the stack works before committing to a model.
- **`ollama`** — real, fully local, private model. No subscription, nothing leaves your machine.
  ```powershell
  ollama pull llama3.1:8b
  ollama pull nomic-embed-text
  ```
  Then in `.env`:
  ```
  MODEL_PROVIDER=ollama
  OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
  OLLAMA_DEFAULT_MODEL=llama3.1:8b
  OLLAMA_EMBEDDING_MODEL=nomic-embed-text
  ```
  `GET /models` queries Ollama's own `/api/tags` live, so pulling additional models (e.g.
  `ollama pull qwen2.5:7b`) makes them selectable in the web app's model dropdown with no backend
  changes. Rebuild/restart the `api` container after editing `.env`:
  `docker compose $envFile -f infrastructure\compose\docker-compose.yml up -d --build api`.
- **`openai`** — any OpenAI-compatible endpoint (OpenAI itself, OpenRouter, a self-hosted vLLM
  server, or Moonshot's Kimi models — their API is documented as OpenAI-compatible, so this needs
  no separate provider, just `OPENAI_BASE_URL=https://api.moonshot.ai/v1` and a real Moonshot key;
  not verified live here, no Moonshot key available to test with). Set `OPENAI_API_KEY` (and
  `OPENAI_BASE_URL` if not using OpenAI directly).
- **`anthropic`** — real Claude models via Anthropic's own Messages API (not an OpenAI-compatible
  endpoint — a separate provider, `services/ai-service/app/ai/anthropic_provider.py`). Set
  `ANTHROPIC_API_KEY` (from [console.anthropic.com](https://console.anthropic.com)) and
  `ANTHROPIC_MODEL` (defaults to `claude-sonnet-5`). Anthropic has no embeddings endpoint, so RAG/
  knowledge search still uses Ollama's embedding model regardless — `OLLAMA_BASE_URL`/
  `OLLAMA_EMBEDDING_MODEL` need to stay set and reachable even when Anthropic is the chat provider.

See [`docs/architecture/self-hosted-model.md`](docs/architecture/self-hosted-model.md) for the
full Ollama integration design.

## Everyday use (after first-time setup)

Start:
```powershell
$envFile = "--env-file", "services\ai-service\.env"
docker compose $envFile -f infrastructure\compose\docker-compose.yml up -d
cd apps\web; npm run dev
```

Stop:
```powershell
docker compose -f infrastructure\compose\docker-compose.yml down
# add -v to also drop the data volumes (destroys all data)
```

**Backend code changes need a rebuild** — the `api` container is a baked image, not hot-reloading:
```powershell
docker compose $envFile -f infrastructure\compose\docker-compose.yml up -d --build api
```
Frontend changes hot-reload automatically via `npm run dev`.

## The coding agent — real, unsandboxed access via host-runner

The Code page (web) and `krixil` (CLI, below) both drive the same coding agent, and both need
`host-runner` running — **read [`services/host-runner/README.md`](services/host-runner/README.md)
first**, it has no approval step and no sandbox: real read/write/execute access to a folder on
your actual machine.

```powershell
cd services\host-runner
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env   # edit HOST_ROOT if you want narrower than the default D:\
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Leave this running in its own terminal whenever you're using the coding agent, either interface.
The sandboxed `code.*` tools this originally sat alongside (an isolated, network-disabled
container, no real machine access) still exist in `services/sandbox-runner` and are unaffected by
any of this — just not wired into either the web Code page or the CLI anymore, per the trade-off
recorded in `docs/architecture/coding-agent.md`.

## Optional: `kirxil`, a terminal coding agent

```powershell
cd cli
npm install
npm run build
npm link       # installs the real `kirxil` command globally
kirxil login   # once — asks for your workspace slug/email/password and your HOST_ROOT
cd D:\some\real\project
kirxil         # interactive; or `kirxil run "<goal>"` for one-shot/scripted use
```

Same backend, same live `⏺ Tool(args)` / `⎿ result` transcript as the web Code page, just in your
terminal — Node.js/TypeScript/Ink, per the CLI product's own PRD
([`docs/architecture/kirxil-cli-prd.md`](docs/architecture/kirxil-cli-prd.md), whose MVP scope is
now fully built). A real Permission Engine pauses for your approval before any HIGH-risk action
(running a shell command, deleting a file); `kirxil checkpoint`/`undo` (real `git` commits) mean a
bad run is always recoverable in a git repo. Beyond `run`, there's a real verb surface —
`kirxil ask/explain/analyze/review/plan` (read-only), `generate/refactor/debug/test/build`, plus
`git`, `search`, `memory`, `config`, `doctor` — see [`cli/README.md`](cli/README.md) for the full
command list and what's built vs. not yet against that PRD.

## Optional: autonomous fine-tuning

`training/` periodically checks whether you have enough real conversation history to fine-tune a
personalized model, and if so, trains, evaluates, and — only if it doesn't regress — promotes a
new model into your dropdown automatically. Needs an NVIDIA GPU. See
[`training/README.md`](training/README.md) for full setup (Unsloth + a CUDA-matched PyTorch build)
and [`docs/architecture/learning-and-memory.md`](docs/architecture/learning-and-memory.md) (Phase
3) for the design. Not required for normal use of the platform.

## Tests, lint, type check

Backend (fully offline — SQLite in-memory + fakeredis + respx, no Docker required):
```powershell
cd services\ai-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
ruff format --check .
ruff check .
mypy app/
```
A handful of RAG/evaluation cases are Postgres-specific (pgvector, full-text search) and are
verified live against the real Docker stack instead — see `docs/architecture/phase2.md`.

Frontend:
```powershell
cd apps\web
npm run lint
npx tsc --noEmit
```

CLI (also fully offline — `fetch` is mocked, no running backend needed):
```powershell
cd cli
npm install
npm test
npm run typecheck
```

## AI evaluation harness

```powershell
docker compose -f infrastructure\compose\docker-compose.yml exec api python scripts/run_evaluations.py
```

Runs a fixed suite of checkable cases (RAG retrieval, citation quality, tool-call selection,
latency, token budget) against a dedicated internal tenant, records the run, and compares it
against the previous baseline. Exits non-zero on any failure or regression — this is what gates
`.github/workflows/ci.yml`'s `build-and-verify` job. See `docs/architecture/phase5.md`.

## CI/CD

`.github/workflows/ci.yml` runs on every push/PR to `main`: lint, type check, unit tests, and a
security scan (dependency + static analysis) run in parallel for both the backend and the
frontend, then a build-and-verify job brings up the real Docker stack, migrates, runs the
evaluation harness, and smoke-tests register→chat. Deploying to staging/production isn't
automated yet — there's no target host to deploy to; see `docs/architecture/phase5.md`.

## Project layout

```
services/ai-service/      the FastAPI backend
services/sandbox-runner/  isolated command execution — not currently used by either coding-agent client (see the coding agent section above), kept for a possible future sandboxed mode
services/host-runner/     real, unsandboxed access to a folder on this machine — native Windows, not Docker; what the coding agent actually runs against now
apps/web/                 the Next.js web UI
cli/                      optional: `kirxil`, a terminal client for the same coding agent — Node.js/TypeScript/Ink, any OS
cli-python/               superseded — the CLI's original Python implementation, kept for reference only
training/                 optional: autonomous fine-tuning scheduler — native Windows, needs a GPU
infrastructure/compose/   Docker Compose stack (api, postgres, redis, minio, prometheus, grafana, jaeger, sandbox-runner)
docs/architecture/        design notes, trade-offs, and the roadmap for each phase
.github/workflows/        CI/CD pipeline
```

## Further reading

Each design decision and its trade-offs are written up in `docs/architecture/`, roughly in the
order features were built:

- `phase0.md`–`phase5.md` — the original backend build: auth/tenancy, chat streaming + short-term
  memory, RAG, the Tool System + human approval, the agent loop, evaluation + observability + CI.
- `web-phase1.md`–`web-phase5.md` — the Next.js frontend, wired against the backend phase by phase.
- `self-hosted-model.md` — running a real local model via Ollama instead of a cloud API.
- `coding-agent.md` — the sandboxed + real-host-access coding agent, git/testing skills.
- `learning-and-memory.md` — cross-conversation memory, the auto-expanding knowledge base, and
  autonomous fine-tuning ("Krixil learns").
- `odysseus-parity.md` — the ongoing feature-parity track (web search, deep research, 2FA, ...).
- `roadmap.md` — chronological index of everything above, and what's next.
