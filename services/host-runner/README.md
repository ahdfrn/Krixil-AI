# host-runner — real, unsandboxed access to a folder on this machine

Runs **natively on Windows**, not in Docker — same reason `training/` does (needs the real host,
not a container). Reached from the `api` container the same way Ollama already is:
`http://host.docker.internal:8002`.

**Read this before running it.** Everything under `HOST_ROOT` (`.env`, default `D:\`) is fully
readable, writable, and executable by the AI — no approval step, no sandbox, real network access.
There is nothing narrower than "stay inside `HOST_ROOT`" protecting the rest of this drive. See
[`docs/architecture/coding-agent.md`](../../docs/architecture/coding-agent.md) ("Real host-folder
access") for the full reasoning behind this trade-off.

## Setup

```powershell
cd services/host-runner
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

Copy-Item .env.example .env
# edit .env if you want a narrower HOST_ROOT than the default D:\
```

## Running

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

`--host 127.0.0.1` is not optional — this service has no authentication of its own, so it must
never bind to `0.0.0.0` or be reachable from outside this machine.

Leave it running in a terminal while using the Code page's "This Computer" mode in the web app;
`code.run_command`'s sandboxed Docker path (the default "Workspace" mode) works fine without it.
