import uuid

from app.models.role import Role
from app.models.user import User
from tests.helpers import auth_headers, register


async def test_list_tools_returns_registered_tools(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.get("/api/v1/tools", headers=headers)
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert names == {"knowledge.search", "usage.get_summary", "document.delete"}


async def test_low_risk_tool_executes_immediately(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post("/api/v1/tools/usage.get_summary/execute", json={"days": 7}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["risk_level"] == "low"
    assert body["output"]["period_days"] == 7


async def test_unknown_tool_returns_404(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post("/api/v1/tools/does.not.exist/execute", json={}, headers=headers)
    assert resp.status_code == 404


async def test_invalid_input_returns_422(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/tools/usage.get_summary/execute", json={"days": "not-a-number"}, headers=headers
    )
    assert resp.status_code == 422


async def test_critical_tool_requires_approval_before_executing(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"content to be deleted via a tool call later", "text/plain")}
    upload = await client.post("/api/v1/documents", files=files, headers=headers)
    document_id = upload.json()["id"]

    resp = await client.post(
        "/api/v1/tools/document.delete/execute", json={"document_id": document_id}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending_approval"
    assert body["risk_level"] == "critical"
    assert body["output"] is None

    list_resp = await client.get("/api/v1/documents", headers=headers)
    assert len(list_resp.json()) == 1


async def test_approving_a_pending_execution_runs_the_tool(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"content to be deleted via approval flow", "text/plain")}
    upload = await client.post("/api/v1/documents", files=files, headers=headers)
    document_id = upload.json()["id"]

    execute_resp = await client.post(
        "/api/v1/tools/document.delete/execute", json={"document_id": document_id}, headers=headers
    )
    execution_id = execute_resp.json()["id"]

    approve_resp = await client.post(f"/api/v1/tools/executions/{execution_id}/approve", headers=headers)

    assert approve_resp.status_code == 200
    body = approve_resp.json()
    assert body["status"] == "completed"
    assert body["output"]["deleted"] is True

    list_resp = await client.get("/api/v1/documents", headers=headers)
    assert list_resp.json() == []


async def test_rejecting_a_pending_execution_does_not_run_the_tool(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"content that should survive rejection", "text/plain")}
    upload = await client.post("/api/v1/documents", files=files, headers=headers)
    document_id = upload.json()["id"]

    execute_resp = await client.post(
        "/api/v1/tools/document.delete/execute", json={"document_id": document_id}, headers=headers
    )
    execution_id = execute_resp.json()["id"]

    reject_resp = await client.post(
        f"/api/v1/tools/executions/{execution_id}/reject",
        json={"reason": "not sure yet"},
        headers=headers,
    )

    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    list_resp = await client.get("/api/v1/documents", headers=headers)
    assert len(list_resp.json()) == 1


async def test_approving_already_resolved_execution_returns_409(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post("/api/v1/tools/usage.get_summary/execute", json={"days": 7}, headers=headers)
    execution_id = resp.json()["id"]

    approve_resp = await client.post(f"/api/v1/tools/executions/{execution_id}/approve", headers=headers)
    assert approve_resp.status_code == 409


async def test_execution_list_and_get_are_tenant_scoped(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@tools.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@tools.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    resp = await client.post("/api/v1/tools/usage.get_summary/execute", json={"days": 7}, headers=headers_a)
    execution_id = resp.json()["id"]

    list_b = await client.get("/api/v1/tools/executions", headers=headers_b)
    assert list_b.json() == []

    get_b = await client.get(f"/api/v1/tools/executions/{execution_id}", headers=headers_b)
    assert get_b.status_code == 404


async def test_missing_permission_returns_403(client, session_factory):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])
    user_id = uuid.UUID(registered["user"]["id"])

    async with session_factory() as session:
        user = await session.get(User, user_id)
        role = await session.get(Role, user.role_id)
        role.permissions = ["something:unrelated"]
        await session.commit()

    resp = await client.post("/api/v1/tools/usage.get_summary/execute", json={"days": 7}, headers=headers)
    assert resp.status_code == 403
