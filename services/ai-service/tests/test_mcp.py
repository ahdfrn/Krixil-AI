import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.mcp import MCPServerCreate
from tests.helpers import auth_headers, register

_TEST_SERVER_SCRIPT = str(Path(__file__).parent / "fixtures" / "mcp_test_server.py")


async def _add_test_server(client, headers, name="test"):
    return await client.post(
        "/api/v1/mcp/servers",
        json={"name": name, "command": sys.executable, "args": [_TEST_SERVER_SCRIPT], "env": {}},
        headers=headers,
    )


async def test_add_list_and_remove_an_mcp_server(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    add_resp = await _add_test_server(client, headers)
    assert add_resp.status_code == 200
    server_id = add_resp.json()["id"]
    assert add_resp.json()["name"] == "test"

    list_resp = await client.get("/api/v1/mcp/servers", headers=headers)
    assert [s["name"] for s in list_resp.json()] == ["test"]

    delete_resp = await client.delete(f"/api/v1/mcp/servers/{server_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp_after = await client.get("/api/v1/mcp/servers", headers=headers)
    assert list_resp_after.json() == []


async def test_adding_a_duplicate_name_returns_409(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await _add_test_server(client, headers)
    dup_resp = await _add_test_server(client, headers)
    assert dup_resp.status_code == 409


def test_stdio_transport_without_command_is_rejected():
    with pytest.raises(ValidationError, match="`command` is required"):
        MCPServerCreate(name="x", transport="stdio")


def test_sse_transport_without_url_is_rejected():
    with pytest.raises(ValidationError, match="`url` is required"):
        MCPServerCreate(name="x", transport="sse")


def test_sse_transport_with_command_is_rejected():
    with pytest.raises(ValidationError, match="only valid for"):
        MCPServerCreate(name="x", transport="sse", url="http://example.com", command="npx")


def test_remote_transport_rejects_a_non_http_url():
    with pytest.raises(ValidationError, match='must start with "http'):
        MCPServerCreate(name="x", transport="sse", url="ftp://example.com")


async def test_header_values_are_redacted_in_api_responses(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/mcp/servers",
        json={
            "name": "remote-with-secret",
            "transport": "sse",
            "url": "http://127.0.0.1:1/sse",
            "headers": {"Authorization": "Bearer super-secret-token"},
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["headers"] == {"Authorization": "***"}
    assert resp.json()["command"] is None


async def test_env_values_are_redacted_in_api_responses(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/mcp/servers",
        json={
            "name": "with-secret",
            "command": sys.executable,
            "args": [_TEST_SERVER_SCRIPT],
            "env": {"API_TOKEN": "super-secret-value"},
        },
        headers=headers,
    )
    assert resp.json()["env"] == {"API_TOKEN": "***"}


async def test_get_server_tools_connects_for_real_and_lists_real_tools(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    add_resp = await _add_test_server(client, headers)
    server_id = add_resp.json()["id"]

    tools_resp = await client.get(f"/api/v1/mcp/servers/{server_id}/tools", headers=headers)
    assert tools_resp.status_code == 200
    names = {t["name"] for t in tools_resp.json()}
    assert names == {"add", "fail"}


async def test_mcp_servers_are_tenant_scoped(client):
    tenant_a = await register(client, tenant_name="MCP Tenant A", email="a@mcp.dev")
    tenant_b = await register(client, tenant_name="MCP Tenant B", email="b@mcp.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    await _add_test_server(client, headers_a)

    list_b = await client.get("/api/v1/mcp/servers", headers=headers_b)
    assert list_b.json() == []


async def test_mcp_list_servers_tool_lists_configured_servers(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])
    await _add_test_server(client, headers)

    resp = await client.post("/api/v1/tools/mcp.list_servers/execute", json={}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["output"]["servers"] == [
        {"name": "test", "transport": "stdio", "command": sys.executable, "url": None}
    ]


async def test_mcp_list_tools_tool_connects_for_real(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])
    await _add_test_server(client, headers)

    resp = await client.post(
        "/api/v1/tools/mcp.list_tools/execute",
        json={"server_name": "test"},
        headers=headers,
    )
    assert resp.status_code == 200
    tool_names = {t["name"] for t in resp.json()["output"]["tools"]}
    assert tool_names == {"add", "fail"}


async def test_mcp_call_tool_is_high_risk_and_pauses_for_approval(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])
    await _add_test_server(client, headers)

    resp = await client.post(
        "/api/v1/tools/mcp.call_tool/execute",
        json={"server_name": "test", "tool_name": "add", "arguments": {"a": 1, "b": 2}},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_level"] == "high"
    assert body["status"] == "pending_approval"

    approve_resp = await client.post(
        f"/api/v1/tools/executions/{body['id']}/approve", headers=headers
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["output"] == {"content": "3", "is_error": False}


async def test_mcp_call_tool_for_an_unknown_server_fails_clearly(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/tools/mcp.call_tool/execute",
        json={"server_name": "does-not-exist", "tool_name": "add", "arguments": {}},
        headers=headers,
    )
    approve = await client.post(
        f"/api/v1/tools/executions/{resp.json()['id']}/approve", headers=headers
    )
    assert approve.json()["status"] == "failed"
    assert "No MCP server named" in approve.json()["error_message"]
