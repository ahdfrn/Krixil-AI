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


async def test_edit_file_replaces_the_unique_occurrence(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await client.post(
        "/api/v1/tools/code.write_file/execute",
        json={"path": "app.py", "content": "def divide(a, b):\n    return a / b\n"},
        headers=headers,
    )

    edit_resp = await client.post(
        "/api/v1/tools/code.edit_file/execute",
        json={
            "path": "app.py",
            "old_string": "return a / b",
            "new_string": "if b == 0:\n        raise ValueError('nope')\n    return a / b",
        },
        headers=headers,
    )
    assert edit_resp.status_code == 200
    edit_body = edit_resp.json()
    assert edit_body["status"] == "completed"
    assert edit_body["risk_level"] == "medium"

    read_resp = await client.post(
        "/api/v1/tools/code.read_file/execute", json={"path": "app.py"}, headers=headers
    )
    assert read_resp.json()["output"]["content"] == (
        "def divide(a, b):\n    if b == 0:\n        raise ValueError('nope')\n    return a / b\n"
    )


async def test_edit_file_fails_clearly_when_old_string_is_ambiguous(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await client.post(
        "/api/v1/tools/code.write_file/execute",
        json={"path": "app.py", "content": "x = 1\nx = 1\n"},
        headers=headers,
    )

    edit_resp = await client.post(
        "/api/v1/tools/code.edit_file/execute",
        json={"path": "app.py", "old_string": "x = 1", "new_string": "x = 2"},
        headers=headers,
    )
    assert edit_resp.status_code == 200
    body = edit_resp.json()
    assert body["status"] == "failed"
    assert "appears 2 times" in body["error_message"]


async def test_edit_file_fails_clearly_when_file_does_not_exist(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/tools/code.edit_file/execute",
        json={"path": "missing.py", "old_string": "x", "new_string": "y"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "does not exist" in body["error_message"]


async def test_search_files_finds_a_real_match(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await client.post(
        "/api/v1/tools/code.write_file/execute",
        json={"path": "src/app.py", "content": "def handler():\n    pass\n"},
        headers=headers,
    )

    resp = await client.post(
        "/api/v1/tools/code.search_files/execute",
        json={"pattern": "def handler"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["risk_level"] == "low"
    assert body["output"]["results"] == [
        {"path": "src/app.py", "line_number": 1, "line": "def handler():"}
    ]


async def test_search_files_surfaces_an_invalid_pattern_error(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/tools/code.search_files/execute",
        json={"pattern": "(unclosed"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "Invalid search pattern" in body["error_message"]


async def test_delete_file_requires_approval_then_actually_deletes_it(
    client, monkeypatch, tmp_path
):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await client.post(
        "/api/v1/tools/code.write_file/execute",
        json={"path": "scratch.py", "content": "x = 1\n"},
        headers=headers,
    )

    delete_resp = await client.post(
        "/api/v1/tools/code.delete_file/execute", json={"path": "scratch.py"}, headers=headers
    )
    assert delete_resp.status_code == 200
    delete_body = delete_resp.json()
    assert delete_body["risk_level"] == "high"
    assert delete_body["status"] == "pending_approval"

    approve_resp = await client.post(
        f"/api/v1/tools/executions/{delete_body['id']}/approve", headers=headers
    )
    assert approve_resp.json()["output"] == {"path": "scratch.py", "deleted": True}

    read_resp = await client.post(
        "/api/v1/tools/code.read_file/execute", json={"path": "scratch.py"}, headers=headers
    )
    assert read_resp.json()["status"] == "failed"


async def test_delete_file_rejects_a_directory(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await client.post(
        "/api/v1/tools/code.write_file/execute",
        json={"path": "a_dir/inside.py", "content": "x = 1\n"},
        headers=headers,
    )

    delete_resp = await client.post(
        "/api/v1/tools/code.delete_file/execute", json={"path": "a_dir"}, headers=headers
    )
    execution_id = delete_resp.json()["id"]

    approve_resp = await client.post(
        f"/api/v1/tools/executions/{execution_id}/approve", headers=headers
    )
    approved_body = approve_resp.json()
    assert approved_body["status"] == "failed"
    assert "is a directory" in approved_body["error_message"]
