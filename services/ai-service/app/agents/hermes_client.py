"""Real HTTP + SSE client for Hermes's own documented "Runs API"
(gateway/platforms/api_server_runs.py in NousResearch/hermes-agent) — verified directly against
that source, not guessed. Hermes runs as its own separate service (never imported as a Python
dependency: its pyproject.toml exact-pins pydantic==2.13.4/httpx==0.28.1, directly incompatible
with this service's own pydantic==2.10.2/httpx==0.27.2 pins in the same venv). A fresh HTTP
connection per call, one long-lived SSE connection per run — same "real, honest error" discipline
as app/mcp/client.py, no fabricated fallback if Hermes is unreachable.
"""

import json
from collections.abc import AsyncIterator

import httpx
from httpx_sse import aconnect_sse

from app.core.config import get_settings


class HermesClientError(Exception):
    """A real, clear failure talking to Hermes — unreachable, misconfigured, or a non-2xx
    response. Never silently swallowed; callers turn this into an honest AgentRun failure."""


def _require_base_url() -> str:
    base_url = get_settings().hermes_base_url
    if not base_url:
        raise HermesClientError(
            "Hermes runtime isn't configured — HERMES_BASE_URL is unset. Set it (and "
            "HERMES_API_KEY) to use runtime=\"hermes\"."
        )
    return base_url.rstrip("/")


def _headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    if settings.hermes_api_key:
        headers["Authorization"] = f"Bearer {settings.hermes_api_key}"
    return headers


async def start_hermes_run(goal: str) -> str:
    """POST /v1/runs {"input": goal} -> the real run_id Hermes assigned."""
    base_url = _require_base_url()
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.hermes_timeout_seconds) as client:
            response = await client.post(
                f"{base_url}/v1/runs", json={"input": goal}, headers=_headers()
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise HermesClientError(f"Couldn't start a Hermes run: {exc}") from exc
    run_id = body.get("run_id")
    if not run_id:
        raise HermesClientError(f"Hermes didn't return a run_id: {body!r}")
    return str(run_id)


async def get_hermes_run_status(run_id: str) -> dict:
    """GET /v1/runs/{run_id} -> the real pollable status dict Hermes reports right now
    ({"object":"hermes.run","run_id","status","session_id","model","output","usage",...})."""
    base_url = _require_base_url()
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.hermes_timeout_seconds) as client:
            response = await client.get(f"{base_url}/v1/runs/{run_id}", headers=_headers())
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HermesClientError(f"Couldn't fetch Hermes run status for {run_id}: {exc}") from exc


async def stream_hermes_events(run_id: str) -> AsyncIterator[dict]:
    """GET /v1/runs/{run_id}/events, text/event-stream — yields the real event dict Hermes pushed
    (each SSE frame's `data:` line is the JSON-encoded event itself, e.g.
    {"event": "tool.started", "run_id": ..., "tool": ..., ...}). Hermes's own documented ": ping"/
    ": keepalive" comment lines and blank keep-alive frames decode to nothing via httpx_sse and are
    skipped automatically — nothing to filter here. The stream ends when Hermes closes the
    connection (its own run reached a terminal state); this generator simply returns then."""
    base_url = _require_base_url()
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with aconnect_sse(
                client,
                "GET",
                f"{base_url}/v1/runs/{run_id}/events",
                headers=_headers(),
                timeout=httpx.Timeout(settings.hermes_timeout_seconds, read=None),
            ) as event_source:
                event_source.response.raise_for_status()
                async for sse in event_source.aiter_sse():
                    if not sse.data:
                        continue
                    try:
                        yield json.loads(sse.data)
                    except json.JSONDecodeError:
                        continue
    except httpx.HTTPError as exc:
        raise HermesClientError(f"Lost the Hermes event stream for run {run_id}: {exc}") from exc


async def resolve_hermes_approval(
    run_id: str, choice: str, request_id: str | None = None
) -> None:
    """POST /v1/runs/{run_id}/approval {"choice": choice}. `choice` is one of Hermes's real
    accepted values ("once"|"session"|"always"|"deny") — this codebase only ever sends "once" or
    "deny" (see app/agents/hermes_runtime.py's confirmed unmapped-tool policy)."""
    base_url = _require_base_url()
    settings = get_settings()
    body: dict = {"choice": choice}
    if request_id:
        body["request_id"] = request_id
    try:
        async with httpx.AsyncClient(timeout=settings.hermes_timeout_seconds) as client:
            response = await client.post(
                f"{base_url}/v1/runs/{run_id}/approval", json=body, headers=_headers()
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HermesClientError(
            f"Couldn't resolve Hermes approval for run {run_id}: {exc}"
        ) from exc


async def stop_hermes_run(run_id: str) -> None:
    """POST /v1/runs/{run_id}/stop -> {"status": "stopping"} — fire-and-forget; Hermes settles the
    run to "cancelled" once its own executor actually exits, observed via the SSE stream/next GET,
    not synchronously here."""
    base_url = _require_base_url()
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.hermes_timeout_seconds) as client:
            response = await client.post(f"{base_url}/v1/runs/{run_id}/stop", headers=_headers())
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HermesClientError(f"Couldn't stop Hermes run {run_id}: {exc}") from exc
