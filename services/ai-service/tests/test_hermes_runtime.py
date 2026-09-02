"""Full POST /agents/run (runtime="hermes") -> real fixture Hermes server -> real AgentStep/
AgentRun/ToolExecution rows, including the real 3-tier permission-bridge policy. Same "real fixture
server, background tasks run to completion under TestClient" pattern already established by
test_swarm.py/test_mcp.py."""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.core.config import get_settings
from tests.helpers import auth_headers, register

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
        monkeypatch.setattr(get_settings(), "hermes_base_url", f"http://127.0.0.1:{port}")
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def _scripted_goal(script: list[dict], final_output: str = "done") -> str:
    return json.dumps({"script": script, "final_output": final_output})


async def test_hermes_runtime_requires_configuration(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])
    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "hello", "runtime": "hermes"}, headers=headers
    )
    assert resp.status_code == 400
    assert "HERMES_BASE_URL" in resp.json()["detail"]


async def test_hermes_run_completes_with_real_tool_steps(client, hermes_server):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    goal = _scripted_goal(
        [
            {"type": "tool.started", "fields": {"tool": "add", "preview": "3 + 4"}},
            {"type": "tool.completed", "fields": {"tool": "add", "duration": 0.05}},
        ],
        final_output="7",
    )
    run_resp = await client.post(
        "/api/v1/agents/run", json={"goal": goal, "runtime": "hermes"}, headers=headers
    )
    assert run_resp.status_code == 200
    assert run_resp.json()["runtime"] == "hermes"
    run_id = run_resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = status_resp.json()
    assert body["status"] == "completed"
    assert body["final_response"] == "7"
    assert body["runtime"] == "hermes"

    step_types = [s["type"] for s in body["steps"]]
    assert step_types == ["tool_call", "observation", "final_response"]
    assert body["steps"][0]["tool_name"] == "add"
    assert "error" not in body["steps"][1]["content"]


async def test_hermes_approval_bridge_blocks_a_known_destructive_command(client, hermes_server):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    goal = _scripted_goal(
        [{"type": "approval.request", "fields": {"tool": "run_command", "command": "rm -rf /"}}]
    )
    run_resp = await client.post(
        "/api/v1/agents/run", json={"goal": goal, "runtime": "hermes"}, headers=headers
    )
    run_id = run_resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = status_resp.json()
    # A real BLOCK match never reaches a human — the run is auto-denied and ends, never
    # "waiting_approval".
    assert body["status"] == "cancelled"

    executions_resp = await client.get("/api/v1/tools/executions", headers=headers)
    assert executions_resp.json() == []


async def test_hermes_approval_bridge_denies_an_opaque_request(client, hermes_server):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    # No "tool"/"name" field at all — insufficient information to evaluate risk.
    goal = _scripted_goal([{"type": "approval.request", "fields": {}}])
    run_resp = await client.post(
        "/api/v1/agents/run", json={"goal": goal, "runtime": "hermes"}, headers=headers
    )
    run_id = run_resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    assert status_resp.json()["status"] == "cancelled"

    executions_resp = await client.get("/api/v1/tools/executions", headers=headers)
    assert executions_resp.json() == []


async def test_hermes_approval_bridge_pauses_for_an_unmapped_tool_and_resumes_on_approval(
    client, hermes_server
):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    goal = _scripted_goal(
        [
            {"type": "approval.request", "fields": {"tool": "write_file", "args": {"path": "x"}}},
            {"type": "tool.completed", "fields": {"tool": "write_file"}},
        ],
        final_output="wrote it",
    )
    run_resp = await client.post(
        "/api/v1/agents/run", json={"goal": goal, "runtime": "hermes"}, headers=headers
    )
    run_id = run_resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    body = status_resp.json()
    assert body["status"] == "waiting_approval"
    execution_id = body["pending_execution_id"]
    assert execution_id is not None

    executions_resp = await client.get("/api/v1/tools/executions", headers=headers)
    executions = executions_resp.json()
    assert len(executions) == 1
    assert executions[0]["tool_name"] == "hermes.write_file"
    assert executions[0]["risk_level"] == "high"
    assert executions[0]["status"] == "pending_approval"
    assert executions[0]["input"]["tool"] == "write_file"

    # Approve through the EXISTING, unmodified /tools/executions/{id}/approve endpoint — proving
    # a Hermes-originated pause resolves through Krixil's own real Permission Engine, not a
    # parallel one.
    approve_resp = await client.post(
        f"/api/v1/tools/executions/{execution_id}/approve", headers=headers
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "running"
    assert approve_resp.json()["completed_at"] is None

    final_status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    final_body = final_status_resp.json()
    assert final_body["status"] == "completed"
    assert final_body["final_response"] == "wrote it"
    executions = (await client.get("/api/v1/tools/executions", headers=headers)).json()
    assert executions[0]["status"] == "completed"
    assert executions[0]["completed_at"] is not None


async def test_hermes_approval_bridge_reject_ends_the_run(client, hermes_server):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    goal = _scripted_goal(
        [{"type": "approval.request", "fields": {"tool": "write_file", "args": {"path": "x"}}}],
        final_output="unreached",
    )
    run_resp = await client.post(
        "/api/v1/agents/run", json={"goal": goal, "runtime": "hermes"}, headers=headers
    )
    run_id = run_resp.json()["id"]

    status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    execution_id = status_resp.json()["pending_execution_id"]

    reject_resp = await client.post(
        f"/api/v1/tools/executions/{execution_id}/reject", json={"reason": "no"}, headers=headers
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    final_status_resp = await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)
    assert final_status_resp.json()["status"] == "stopped"


@pytest.mark.parametrize(
    "event",
    [
        {"tool": "execute", "args": {}},
        {"tool": "execute", "args": {"directory": "."}},
        {"tool": "write_file", "arguments": "invalid json"},
        {"tool": "run_command", "args": {"command": "rm -rf /"}},
        {"tool": "run_command", "arguments": '{"command":"rm -rf /"}'},
    ],
)
def test_unsafe_or_opaque_approval_is_denied(event):
    from app.agents.hermes_runtime import classify_hermes_approval

    risk, reason = classify_hermes_approval(event)
    assert risk is None
    assert reason


@pytest.mark.parametrize("missing_result", [False, True])
async def test_hermes_failed_result_updates_execution(client, hermes_server, missing_result):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])
    script = [
        {"type": "approval.request", "fields": {"tool": "write_file", "args": {"path": "x"}}},
        {
            "type": "tool.completed",
            "fields": {"tool": "write_file", "error": "Permission denied"},
        },
    ]
    if missing_result:
        script.pop()
    goal = _scripted_goal(script)
    run = (
        await client.post(
            "/api/v1/agents/run", json={"goal": goal, "runtime": "hermes"}, headers=headers
        )
    ).json()
    state = (await client.get(f"/api/v1/agents/{run['id']}/status", headers=headers)).json()
    await client.post(
        f"/api/v1/tools/executions/{state['pending_execution_id']}/approve", headers=headers
    )
    execution = (await client.get("/api/v1/tools/executions", headers=headers)).json()[0]
    assert execution["status"] == "failed"
    expected = (
        "Hermes stream ended without a matching tool result"
        if missing_result
        else "Permission denied"
    )
    assert execution["error_message"] == expected
