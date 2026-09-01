import json

import httpx
import respx

from app.core.config import Settings
from tests.helpers import auth_headers, register


def _override_host_runner(monkeypatch, url: str = "http://host-runner.test"):
    monkeypatch.setattr(
        "app.tools.host_tools.get_settings", lambda: Settings(host_runner_url=url)
    )


async def test_host_tools_are_registered(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.get("/api/v1/tools", headers=headers)
    names = {t["name"] for t in resp.json()}
    assert {
        "host.list_files",
        "host.read_file",
        "host.write_file",
        "host.edit_file",
        "host.search_files",
        "host.delete_file",
        "host.run_command",
    } <= names


async def test_host_write_file_executes_immediately_no_approval(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://host-runner.test/files").mock(
            return_value=httpx.Response(
                201, json={"path": "demo/hello.py", "content": "print('hi')\n"}
            )
        )
        resp = await client.post(
            "/api/v1/tools/host.write_file/execute",
            json={"path": "demo/hello.py", "content": "print('hi')\n"},
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_level"] == "medium"
    assert body["status"] == "completed"
    assert body["output"] == {"path": "demo/hello.py", "written": True}


async def test_host_run_command_requires_approval_before_executing(client, monkeypatch):
    """HIGH risk (app/tools/host_tools.py) — arbitrary shell execution is a bigger blast radius
    than a single file write, and it's the Permission Engine's own example of a HIGH-risk action
    (docs/architecture/kirxil-cli-prd.md §17). Unlike host.write_file, this one has to actually
    pause and wait for a human before host-runner ever sees the command."""
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=False) as mock:
        run_route = mock.post("http://host-runner.test/run").mock(
            return_value=httpx.Response(
                200, json={"stdout": "hi\n", "stderr": "", "exit_code": 0, "timed_out": False}
            )
        )
        resp = await client.post(
            "/api/v1/tools/host.run_command/execute",
            json={"directory": "demo", "command": "python hello.py"},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_level"] == "high"
        assert body["status"] == "pending_approval"
        assert run_route.call_count == 0

        approve_resp = await client.post(
            f"/api/v1/tools/executions/{body['id']}/approve", headers=headers
        )
        assert approve_resp.status_code == 200
        approved_body = approve_resp.json()
        assert approved_body["status"] == "completed"
        assert approved_body["output"] == {
            "stdout": "hi\n",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
        }
        assert run_route.call_count == 1


async def test_host_run_command_rejection_never_calls_host_runner(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=False) as mock:
        run_route = mock.post("http://host-runner.test/run").mock(
            return_value=httpx.Response(200, json={"stdout": "", "stderr": "", "exit_code": 0})
        )
        resp = await client.post(
            "/api/v1/tools/host.run_command/execute",
            json={"directory": "demo", "command": "rm -rf ."},
            headers=headers,
        )
        execution_id = resp.json()["id"]

        reject_resp = await client.post(
            f"/api/v1/tools/executions/{execution_id}/reject",
            json={"reason": "too dangerous"},
            headers=headers,
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"
        assert run_route.call_count == 0


async def test_host_edit_file_replaces_the_unique_occurrence(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/files/content").mock(
            return_value=httpx.Response(
                200, json={"path": "app.py", "content": "def divide(a, b):\n    return a / b\n"}
            )
        )
        write_route = mock.post("http://host-runner.test/files").mock(
            return_value=httpx.Response(201, json={"path": "app.py", "content": "irrelevant"})
        )
        resp = await client.post(
            "/api/v1/tools/host.edit_file/execute",
            json={
                "path": "app.py",
                "old_string": "return a / b",
                "new_string": (
                    "if b == 0:\n        raise ValueError('division by zero')\n    return a / b"
                ),
            },
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["risk_level"] == "medium"
    assert body["output"] == {"path": "app.py", "edited": True}

    sent_body = json.loads(write_route.calls.last.request.content)
    assert sent_body["content"] == (
        "def divide(a, b):\n    if b == 0:\n        raise ValueError('division by zero')\n"
        "    return a / b\n"
    )


async def test_host_edit_file_fails_clearly_when_old_string_is_missing(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/files/content").mock(
            return_value=httpx.Response(200, json={"path": "app.py", "content": "print('hi')\n"})
        )
        resp = await client.post(
            "/api/v1/tools/host.edit_file/execute",
            json={"path": "app.py", "old_string": "not in the file", "new_string": "x"},
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "not found" in body["error_message"]


async def test_host_edit_file_fails_clearly_when_old_string_is_ambiguous(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/files/content").mock(
            return_value=httpx.Response(
                200, json={"path": "app.py", "content": "x = 1\nx = 1\n"}
            )
        )
        resp = await client.post(
            "/api/v1/tools/host.edit_file/execute",
            json={"path": "app.py", "old_string": "x = 1", "new_string": "x = 2"},
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "appears 2 times" in body["error_message"]


async def test_host_search_files_returns_matches(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("http://host-runner.test/search").mock(
            return_value=httpx.Response(
                200,
                json=[{"path": "app.py", "line_number": 3, "line": "def handler():"}],
            )
        )
        resp = await client.post(
            "/api/v1/tools/host.search_files/execute",
            json={"pattern": "def handler", "path": "."},
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["risk_level"] == "low"
    assert body["output"] == {
        "results": [{"path": "app.py", "line_number": 3, "line": "def handler():"}]
    }
    assert route.calls.last.request.url.params["pattern"] == "def handler"


async def test_host_search_files_surfaces_an_invalid_pattern_error(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/search").mock(
            return_value=httpx.Response(400, json={"detail": "Invalid search pattern: bad regex"})
        )
        resp = await client.post(
            "/api/v1/tools/host.search_files/execute",
            json={"pattern": "(unclosed", "path": "."},
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "Invalid search pattern" in body["error_message"]


async def test_host_delete_file_requires_approval_before_deleting(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=False) as mock:
        delete_route = mock.delete("http://host-runner.test/files").mock(
            return_value=httpx.Response(204)
        )
        resp = await client.post(
            "/api/v1/tools/host.delete_file/execute",
            json={"path": "scratch/old.py"},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_level"] == "high"
        assert body["status"] == "pending_approval"
        assert delete_route.call_count == 0

        approve_resp = await client.post(
            f"/api/v1/tools/executions/{body['id']}/approve", headers=headers
        )
        assert approve_resp.status_code == 200
        approved_body = approve_resp.json()
        assert approved_body["status"] == "completed"
        assert approved_body["output"] == {"path": "scratch/old.py", "deleted": True}
        assert delete_route.call_count == 1
        assert delete_route.calls.last.request.url.params["path"] == "scratch/old.py"


async def test_host_delete_file_rejection_never_calls_host_runner(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=False) as mock:
        delete_route = mock.delete("http://host-runner.test/files").mock(
            return_value=httpx.Response(204)
        )
        resp = await client.post(
            "/api/v1/tools/host.delete_file/execute",
            json={"path": "important.py"},
            headers=headers,
        )
        execution_id = resp.json()["id"]

        reject_resp = await client.post(
            f"/api/v1/tools/executions/{execution_id}/reject",
            json={"reason": "not that one"},
            headers=headers,
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"
        assert delete_route.call_count == 0


async def test_host_read_file_surfaces_path_confinement_error(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/files/content").mock(
            return_value=httpx.Response(
                400, json={"detail": "'C:/Windows' is outside HOST_ROOT (D:\\)"}
            )
        )
        resp = await client.post(
            "/api/v1/tools/host.read_file/execute",
            json={"path": "C:/Windows/win.ini"},
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "outside HOST_ROOT" in body["error_message"]
