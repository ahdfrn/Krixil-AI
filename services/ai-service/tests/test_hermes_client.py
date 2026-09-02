"""Real subprocess, real HTTP+SSE round trip — tests/fixtures/hermes_fixture_server.py implements
Hermes's own real documented Runs API shape (verified against the real source), not a mock. Same
discipline as test_mcp_client_remote.py."""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.agents.hermes_client import (
    HermesClientError,
    get_hermes_run_status,
    resolve_hermes_approval,
    start_hermes_run,
    stop_hermes_run,
    stream_hermes_events,
)
from app.core.config import get_settings

_FIXTURE_SCRIPT = str(Path(__file__).parent / "fixtures" / "hermes_fixture_server.py")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError as exc:
            last_exc = exc
            time.sleep(0.1)
    raise RuntimeError(f"hermes fixture server never came up on port {port}") from last_exc


@pytest.fixture
def hermes_server(monkeypatch):
    port = _free_port()
    proc = subprocess.Popen([sys.executable, _FIXTURE_SCRIPT, str(port)])
    try:
        _wait_until_up(port)
        base_url = f"http://127.0.0.1:{port}"
        monkeypatch.setattr(get_settings(), "hermes_base_url", base_url)
        yield base_url
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def _simple_run_input() -> str:
    return json.dumps(
        {
            "script": [
                {"type": "tool.started", "fields": {"tool": "add", "preview": "3 + 4"}},
                {"type": "tool.completed", "fields": {"tool": "add", "duration": 0.1}},
            ],
            "final_output": "7",
        }
    )


async def test_start_hermes_run_returns_a_real_run_id(hermes_server):
    run_id = await start_hermes_run(_simple_run_input())
    assert run_id.startswith("run_")


async def test_get_hermes_run_status_reflects_the_real_final_state(hermes_server):
    run_id = await start_hermes_run(_simple_run_input())
    # Drain the real event stream so the fixture's background task actually reaches "completed"
    # before we poll status — same reasoning any real Hermes client needs.
    async for _event in stream_hermes_events(run_id):
        pass
    status = await get_hermes_run_status(run_id)
    assert status["status"] == "completed"
    assert status["output"] == "7"


async def test_stream_hermes_events_yields_the_real_scripted_events(hermes_server):
    run_id = await start_hermes_run(_simple_run_input())
    events = [event async for event in stream_hermes_events(run_id)]
    kinds = [e["event"] for e in events]
    assert kinds == ["tool.started", "tool.completed"]
    assert events[0]["tool"] == "add"


async def test_resolve_hermes_approval_lets_a_paused_run_continue(hermes_server):
    goal = json.dumps(
        {
            "script": [
                {
                    "type": "approval.request",
                    "fields": {"tool": "write_file", "command": "echo hi"},
                },
                {"type": "tool.completed", "fields": {"tool": "write_file"}},
            ],
            "final_output": "wrote it",
        }
    )
    run_id = await start_hermes_run(goal)

    events = []
    async for event in stream_hermes_events(run_id):
        events.append(event)
        if event["event"] == "approval.request":
            await resolve_hermes_approval(run_id, "once")

    assert [e["event"] for e in events] == ["approval.request", "tool.completed"]
    status = await get_hermes_run_status(run_id)
    assert status["status"] == "completed"
    assert status["output"] == "wrote it"


async def test_resolve_hermes_approval_deny_ends_the_run(hermes_server):
    goal = json.dumps(
        {
            "script": [{"type": "approval.request", "fields": {"tool": "write_file"}}],
            "final_output": "should not be reached",
        }
    )
    run_id = await start_hermes_run(goal)

    async for event in stream_hermes_events(run_id):
        if event["event"] == "approval.request":
            await resolve_hermes_approval(run_id, "deny")

    status = await get_hermes_run_status(run_id)
    assert status["status"] == "cancelled"


async def test_stop_hermes_run_returns_stopping(hermes_server):
    run_id = await start_hermes_run(_simple_run_input())
    await stop_hermes_run(run_id)  # doesn't raise


async def test_start_hermes_run_raises_a_clear_error_for_an_unreachable_url(monkeypatch):
    monkeypatch.setattr(get_settings(), "hermes_base_url", "http://127.0.0.1:1")
    with pytest.raises(HermesClientError, match="Couldn't start a Hermes run"):
        await start_hermes_run(_simple_run_input())


async def test_start_hermes_run_raises_a_clear_error_when_unconfigured(monkeypatch):
    monkeypatch.setattr(get_settings(), "hermes_base_url", "")
    with pytest.raises(HermesClientError, match="isn't configured"):
        await start_hermes_run(_simple_run_input())
