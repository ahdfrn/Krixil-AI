from app.core.config import get_settings
from tests.helpers import auth_headers, register


async def test_agent_completes_without_calling_a_tool(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "what's the weather like today?"}, headers=headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["tool_call_count"] == 0
    assert body["final_response"]


async def test_agent_calls_low_risk_tool_and_completes(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "please give me a usage summary"}, headers=headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["tool_call_count"] == 1

    status_resp = await client.get(f"/api/v1/agents/{body['id']}/status", headers=headers)
    steps = status_resp.json()["steps"]
    types = [s["type"] for s in steps]
    assert "tool_call" in types
    assert "observation" in types
    assert any(s["tool_name"] == "usage.get_summary" for s in steps if s["tool_name"])


async def test_agent_stops_when_tool_call_budget_exceeded(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_max_tool_calls", 0)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "please give me a usage summary"}, headers=headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "stopped"
    assert "max_tool_calls" in body["error_message"]


async def test_agent_stops_when_step_budget_exceeded(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_max_steps", 1)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "please give me a usage summary"}, headers=headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "stopped"
    assert "max_steps" in body["error_message"]


async def test_agent_stops_waiting_approval_for_critical_tool_and_does_not_execute_it(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"content that an agent will try to delete", "text/plain")}
    upload = await client.post("/api/v1/documents", files=files, headers=headers)
    document_id = upload.json()["id"]

    resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": f"please delete document {document_id}"},
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "waiting_approval"
    assert body["pending_execution_id"]

    list_resp = await client.get("/api/v1/documents", headers=headers)
    assert len(list_resp.json()) == 1


async def test_approving_agents_pending_tool_actually_executes_it(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"content the agent will delete after approval", "text/plain")}
    upload = await client.post("/api/v1/documents", files=files, headers=headers)
    document_id = upload.json()["id"]

    run_resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": f"please delete document {document_id}"},
        headers=headers,
    )
    execution_id = run_resp.json()["pending_execution_id"]

    approve_resp = await client.post(
        f"/api/v1/tools/executions/{execution_id}/approve", headers=headers
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["output"]["deleted"] is True

    list_resp = await client.get("/api/v1/documents", headers=headers)
    assert list_resp.json() == []


async def test_agent_handles_a_failed_tool_call_without_crashing(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    # "delete" matches document.delete's keyword, but there's no UUID in the message, so
    # MockProvider can't fill the required document_id — the tool call should fail schema
    # validation and the agent should record that as an observation, not crash the request.
    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "please delete the document"}, headers=headers
    )

    assert resp.status_code == 200
    status_resp = await client.get(f"/api/v1/agents/{resp.json()['id']}/status", headers=headers)
    steps = status_resp.json()["steps"]
    error_observations = [
        s
        for s in steps
        if s["type"] == "observation"
        and s["tool_name"] == "document.delete"
        and "error" in s["content"]
    ]
    assert len(error_observations) == 1


async def test_agent_runs_and_status_are_tenant_scoped(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@agents.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@agents.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    resp = await client.post("/api/v1/agents/run", json={"goal": "hello"}, headers=headers_a)
    agent_run_id = resp.json()["id"]

    list_b = await client.get("/api/v1/agents", headers=headers_b)
    assert list_b.json() == []

    status_b = await client.get(f"/api/v1/agents/{agent_run_id}/status", headers=headers_b)
    assert status_b.status_code == 404
