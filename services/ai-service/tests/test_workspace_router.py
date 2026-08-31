from app.core.config import Settings
from tests.helpers import auth_headers, register


async def _override_workspace_root(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.workspace.fs.get_settings", lambda: Settings(workspace_root=str(tmp_path))
    )


async def test_upload_list_and_delete_round_trip(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("hello.py", b"print('hi')\n", "text/plain")}
    upload_resp = await client.post(
        "/api/v1/workspace/files", params={"path": "hello.py"}, files=files, headers=headers
    )
    assert upload_resp.status_code == 201
    assert upload_resp.json()["content"] == "print('hi')\n"

    list_resp = await client.get("/api/v1/workspace/files", headers=headers)
    assert list_resp.status_code == 200
    assert [e["path"] for e in list_resp.json()] == ["hello.py"]

    content_resp = await client.get(
        "/api/v1/workspace/files/content", params={"path": "hello.py"}, headers=headers
    )
    assert content_resp.status_code == 200
    assert content_resp.json()["content"] == "print('hi')\n"

    delete_resp = await client.request(
        "DELETE", "/api/v1/workspace/files", params={"path": "hello.py"}, headers=headers
    )
    assert delete_resp.status_code == 204

    list_after = await client.get("/api/v1/workspace/files", headers=headers)
    assert list_after.json() == []


async def test_files_are_tenant_scoped(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    tenant_a = await register(client, tenant_name="Tenant A", email="a@workspace.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@workspace.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    files = {"file": ("secret.py", b"tenant a's data", "text/plain")}
    await client.post(
        "/api/v1/workspace/files", params={"path": "secret.py"}, files=files, headers=headers_a
    )

    list_b = await client.get("/api/v1/workspace/files", headers=headers_b)
    assert list_b.json() == []

    content_b = await client.get(
        "/api/v1/workspace/files/content", params={"path": "secret.py"}, headers=headers_b
    )
    assert content_b.status_code == 404


async def test_content_of_missing_file_returns_404(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.get(
        "/api/v1/workspace/files/content", params={"path": "nope.py"}, headers=headers
    )
    assert resp.status_code == 404


async def test_traversal_via_router_is_rejected(client, monkeypatch, tmp_path):
    await _override_workspace_root(monkeypatch, tmp_path)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.get(
        "/api/v1/workspace/files/content",
        params={"path": "../../etc/passwd"},
        headers=headers,
    )
    assert resp.status_code == 400
