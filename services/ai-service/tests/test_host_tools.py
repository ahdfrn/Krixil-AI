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
    assert {"host.list_files", "host.read_file", "host.write_file", "host.run_command"} <= names


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


async def test_host_run_command_executes_immediately_no_approval(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://host-runner.test/run").mock(
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
    assert body["status"] == "completed"
    assert body["output"] == {"stdout": "hi\n", "stderr": "", "exit_code": 0, "timed_out": False}


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
