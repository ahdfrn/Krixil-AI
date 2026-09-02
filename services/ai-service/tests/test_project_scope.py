import uuid
from urllib.parse import quote

import httpx
import respx

from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.tool_execution import ToolExecution
from tests.helpers import auth_headers, register

ROOT = r"E:\Projects\Example"


async def test_host_browsing_requires_login(client):
    response = await client.get("/api/v1/host/files")
    assert response.status_code == 401


async def test_workspace_handshake_forwards_authenticated_scope(client):
    account = await register(client)
    headers = {**auth_headers(account["access_token"]), "X-Krixil-Workspace": quote(ROOT, safe="")}
    with respx.mock() as mock:
        route = mock.get(f"{get_settings().host_runner_url}/workspace").mock(
            return_value=httpx.Response(200, json={"root": ROOT})
        )
        response = await client.get("/api/v1/host/workspace", headers=headers)
        assert response.status_code == 200
        assert route.calls.last.request.headers["X-Krixil-Workspace"] == quote(ROOT, safe="")
        assert "X-Krixil-Host-Key" in route.calls.last.request.headers


async def test_approval_uses_original_folder_not_approvers_current_folder(client, session_factory):
    account = await register(client)
    headers = {**auth_headers(account["access_token"]), "X-Krixil-Workspace": quote(ROOT, safe="")}
    response = await client.post(
        "/api/v1/tools/host.run_command/execute",
        headers=headers,
        json={"directory": ".", "command": "echo test"},
    )
    assert response.status_code == 200
    execution_id = response.json()["id"]
    assert response.json()["status"] == "pending_approval"
    async with session_factory() as session:
        execution = await session.get(ToolExecution, uuid.UUID(execution_id))
        assert execution.workspace_root == ROOT
    headers["X-Krixil-Workspace"] = quote(r"D:\Other", safe="")
    with respx.mock() as mock:
        route = mock.post(f"{get_settings().host_runner_url}/run").mock(
            return_value=httpx.Response(
                200, json={"stdout": "test", "stderr": "", "exit_code": 0, "timed_out": False}
            )
        )
        result = await client.post(
            f"/api/v1/tools/executions/{execution_id}/approve", headers=headers
        )
        assert result.status_code == 200
        assert result.json()["status"] == "completed"
        assert route.calls.last.request.headers["X-Krixil-Workspace"] == quote(ROOT, safe="")


async def test_agent_persists_scope_and_rejects_escape_tool(client, session_factory):
    account = await register(client)
    headers = {**auth_headers(account["access_token"]), "X-Krixil-Workspace": quote(ROOT, safe="")}
    response = await client.post("/api/v1/agents/run", headers=headers, json={"goal": "hello"})
    assert response.status_code == 200
    async with session_factory() as session:
        run = await session.get(AgentRun, uuid.UUID(response.json()["id"]))
        assert run.workspace_root == ROOT
    response = await client.post(
        "/api/v1/tools/code.read_file/execute", headers=headers, json={"path": "secret"}
    )
    assert response.status_code == 403


async def test_unscoped_runtime_does_not_silently_escape_project(client):
    account = await register(client)
    headers = {**auth_headers(account["access_token"]), "X-Krixil-Workspace": quote(ROOT, safe="")}
    response = await client.post(
        "/api/v1/agents/run", headers=headers, json={"goal": "hello", "runtime": "hermes"}
    )
    assert response.status_code == 400


async def test_native_background_and_resume_keep_original_scope(client, monkeypatch):
    from unittest.mock import AsyncMock

    import app.agents.router as agents_router
    from app.ai.base import ModelResponse, ToolCallRequest

    provider = AsyncMock()
    provider.name = "test"
    provider.tool_call.side_effect = [
        ModelResponse(
            content="",
            model="test",
            tool_calls=[
                ToolCallRequest(
                    name="host.run_command", arguments={"directory": ".", "command": "echo test"}
                )
            ],
        ),
        ModelResponse(
            content="",
            model="test",
            tool_calls=[ToolCallRequest(name="host.read_file", arguments={"path": "name.txt"})],
        ),
        ModelResponse(content="done", model="test"),
    ]
    monkeypatch.setattr(agents_router.model_router, "get_provider", lambda: provider)
    account = await register(client)
    headers = {**auth_headers(account["access_token"]), "X-Krixil-Workspace": quote(ROOT, safe="")}
    response = await client.post("/api/v1/agents/run", headers=headers, json={"goal": "test"})
    assert response.status_code == 200
    run_id = response.json()["id"]
    run = (await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)).json()
    assert run["status"] == "waiting_approval"
    headers["X-Krixil-Workspace"] = quote(r"D:\Other", safe="")
    with respx.mock() as mock:
        command = mock.post(f"{get_settings().host_runner_url}/run").mock(
            return_value=httpx.Response(
                200, json={"stdout": "test", "stderr": "", "exit_code": 0, "timed_out": False}
            )
        )
        read = mock.get(f"{get_settings().host_runner_url}/files/content").mock(
            return_value=httpx.Response(200, json={"path": "name.txt", "content": "test"})
        )
        result = await client.post(
            f"/api/v1/tools/executions/{run['pending_execution_id']}/approve", headers=headers
        )
        assert result.status_code == 200
        for route in (command, read):
            assert route.calls.last.request.headers["X-Krixil-Workspace"] == quote(ROOT, safe="")
    run = (await client.get(f"/api/v1/agents/{run_id}/status", headers=headers)).json()
    assert run["status"] == "completed"
    assert all(tool.name.startswith("host.") for tool in provider.tool_call.call_args.args[1])
