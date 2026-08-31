"""The only component in this stack that touches the Docker socket. It exists specifically so
that privilege never has to be granted to the main api container — see
docs/architecture/coding-agent.md for the reasoning. Every command it runs happens inside a fresh,
network-disabled, resource-limited container that is force-removed afterward; nothing here
executes directly on this container's own filesystem or process space."""

import os
import socket
from pathlib import Path

import docker
from docker.errors import NotFound
from fastapi import FastAPI
from pydantic import BaseModel, Field
from requests.exceptions import ReadTimeout

WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", "/workspaces"))
# Built from runner-image/Dockerfile (git, build-essential, pytest — not a bare python:3.11-slim,
# which had none of those and made things like `git commit` or running a test suite fail outright
# with "command not found"). Must be built locally first (`docker build -t krixil-sandbox-python:
# latest runner-image/`) — it's not on a public registry, so containers.run() can't just pull it.
RUNNER_IMAGE = "krixil-sandbox-python:latest"
MEM_LIMIT = "256m"
CPU_PERIOD = 100_000
CPU_QUOTA = 50_000  # 50% of one CPU

app = FastAPI(title="krixil-sandbox-runner")
docker_client = docker.from_env()

_workspace_volume_name: str | None = None


def _resolve_workspace_volume_name() -> str:
    """The name Compose actually gives the `workspaces` volume is project-prefixed (e.g.
    `krixil_workspaces`), not the literal `workspaces` from docker-compose.yml — passing that
    literal name straight to `containers.run(volumes=...)` silently creates and mounts a brand
    new, empty, wrongly-named volume instead of the real shared one (caught live: files written
    by the api container were invisible here). Resolved once by asking the Docker API what
    volume is actually mounted at /workspaces on *this* container, rather than hardcoding a
    project-name-dependent string."""
    global _workspace_volume_name
    if _workspace_volume_name is None:
        self_container = docker_client.containers.get(socket.gethostname())
        for mount in self_container.attrs.get("Mounts", []):
            if mount.get("Destination") == "/workspaces":
                _workspace_volume_name = mount["Name"]
                break
        else:
            raise RuntimeError("sandbox-runner has no /workspaces volume mounted")
    return _workspace_volume_name


class RunRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    command: str = Field(min_length=1, max_length=2000)
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class RunResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/run", response_model=RunResult)
async def run_command(payload: RunRequest) -> RunResult:
    tenant_workspace = WORKSPACE_ROOT / payload.tenant_id
    tenant_workspace.mkdir(parents=True, exist_ok=True)

    # The whole workspaces volume is mounted (not a per-tenant bind) because this is the same
    # named volume the api container writes to, and docker-py's `volumes=` here is resolved by
    # the HOST daemon, not by this container's own filesystem view — a per-tenant subpath mount
    # needs a Docker Engine new enough to support volume-subpath mounts, which isn't guaranteed.
    # working_dir scopes the command to the tenant's own directory; tightening this to a real
    # per-tenant mount is a natural follow-up once this app is more than single-tenant.
    container = docker_client.containers.run(
        RUNNER_IMAGE,
        ["sh", "-c", payload.command],
        working_dir=f"/workspaces/{payload.tenant_id}",
        volumes={_resolve_workspace_volume_name(): {"bind": "/workspaces", "mode": "rw"}},
        network_mode="none",
        mem_limit=MEM_LIMIT,
        cpu_period=CPU_PERIOD,
        cpu_quota=CPU_QUOTA,
        detach=True,
    )

    timed_out = False
    exit_code = -1
    try:
        result = container.wait(timeout=payload.timeout_seconds)
        exit_code = result.get("StatusCode", -1)
    except ReadTimeout:
        timed_out = True
        try:
            container.kill()
        except NotFound:
            pass

    stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
    stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
    container.remove(force=True)

    return RunResult(stdout=stdout, stderr=stderr, exit_code=exit_code, timed_out=timed_out)
