import httpx
import respx

from app.core.config import Settings
from tests.helpers import auth_headers, register


async def _override_workspace_root(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.workspace.fs.get_settings", lambda: Settings(workspace_root=str(tmp_path))
    )


async def test_write_then_read_file_round_trip(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    # MEDIUM risk (not CRITICAL): runs immediately, no approval step — an explicit tradeoff for
    # uninterrupted multi-step agent use, made after being told what it means. See
    # app/tools/code_tools.py.
    write_resp = await client.post(
        "/api/v1/tools/code.write_file/execute",
        json={"path": "hello.py", "content": "print('hi')\n"},
        headers=headers,
    )
    assert write_resp.status_code == 200
    write_body = write_resp.json()
    assert write_body["status"] == "completed"
    assert write_body["risk_level"] == "medium"

    read_resp = await client.post(
        "/api/v1/tools/code.read_file/execute", json={"path": "hello.py"}, headers=headers
    )
    assert read_resp.status_code == 200
    body = read_resp.json()
    assert body["status"] == "completed"
    assert body["output"]["content"] == "print('hi')\n"


async def test_list_files_is_low_risk_and_executes_immediately(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post("/api/v1/tools/code.list_files/execute", json={}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["risk_level"] == "low"
    assert body["output"]["entries"] == []


async def test_read_file_rejects_path_traversal(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/tools/code.read_file/execute",
        json={"path": "../../etc/passwd"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "outside the workspace" in body["error_message"]


async def test_write_file_rejects_path_traversal(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/tools/code.write_file/execute",
        json={"path": "../../etc/passwd", "content": "pwned"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "outside the workspace" in body["error_message"]


async def test_run_command_executes_immediately_and_calls_sandbox_runner(
    client, monkeypatch, tmp_path
):
    await _override_workspace_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.tools.code_tools.get_settings",
        lambda: Settings(
            workspace_root=str(tmp_path), sandbox_runner_url="http://sandbox-runner.test"
        ),
    )
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://sandbox-runner.test/run").mock(
            return_value=httpx.Response(
                200, json={"stdout": "hi\n", "stderr": "", "exit_code": 0, "timed_out": False}
            )
        )
        execute_resp = await client.post(
            "/api/v1/tools/code.run_command/execute",
            json={"command": "echo hi"},
            headers=headers,
        )

    assert execute_resp.status_code == 200
    body = execute_resp.json()
    assert body["risk_level"] == "medium"
    assert body["status"] == "completed"
    assert body["output"] == {"stdout": "hi\n", "stderr": "", "exit_code": 0, "timed_out": False}


async def test_run_command_reports_sandbox_runner_failure(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.tools.code_tools.get_settings",
        lambda: Settings(
            workspace_root=str(tmp_path), sandbox_runner_url="http://sandbox-runner.test"
        ),
    )
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://sandbox-runner.test/run").mock(return_value=httpx.Response(503))
        execute_resp = await client.post(
            "/api/v1/tools/code.run_command/execute",
            json={"command": "echo hi"},
            headers=headers,
        )

    assert execute_resp.status_code == 200
    assert execute_resp.json()["status"] == "failed"
