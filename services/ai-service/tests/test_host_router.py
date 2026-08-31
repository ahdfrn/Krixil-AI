import httpx
import respx

from app.core.config import Settings
from tests.helpers import auth_headers, register


def _override_host_runner(monkeypatch, url: str = "http://host-runner.test"):
    monkeypatch.setattr(
        "app.workspace.host_router.get_settings", lambda: Settings(host_runner_url=url)
    )


async def test_list_files_proxies_to_host_runner(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/files").mock(
            return_value=httpx.Response(
                200, json=[{"name": "demo", "path": "demo", "is_dir": True, "size_bytes": None}]
            )
        )
        resp = await client.get("/api/v1/host/files", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == [{"name": "demo", "path": "demo", "is_dir": True, "size_bytes": None}]


async def test_host_runner_unreachable_returns_503(client, monkeypatch):
    _override_host_runner(monkeypatch, url="http://127.0.0.1:1")
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.get("/api/v1/host/files", headers=headers)
    assert resp.status_code == 503
    assert "host-runner isn't reachable" in resp.json()["detail"]


async def test_path_confinement_error_is_forwarded_as_400(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/files/content").mock(
            return_value=httpx.Response(
                400, json={"detail": "'C:/Windows' is outside HOST_ROOT (D:\\)"}
            )
        )
        resp = await client.get(
            "/api/v1/host/files/content", params={"path": "C:/Windows/win.ini"}, headers=headers
        )

    assert resp.status_code == 400
    assert "outside HOST_ROOT" in resp.json()["detail"]


async def test_upload_file_proxies_content_to_host_runner(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://host-runner.test/files").mock(
            return_value=httpx.Response(
                201, json={"path": "demo/hello.py", "content": "print('hi')\n"}
            )
        )
        files = {"file": ("hello.py", b"print('hi')\n", "text/plain")}
        resp = await client.post(
            "/api/v1/host/files",
            params={"path": "demo/hello.py"},
            files=files,
            headers=headers,
        )

    assert resp.status_code == 201
    assert resp.json() == {"path": "demo/hello.py", "content": "print('hi')\n"}
    sent_body = route.calls[0].request.content.decode("utf-8")
    assert "print('hi')" in sent_body
