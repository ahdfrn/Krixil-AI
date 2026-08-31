import uuid

from app.memory.long_term import build_memory_context
from app.tenancy.context import TenantContext
from tests.helpers import auth_headers, register


async def test_create_list_delete_memory(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    create_resp = await client.post(
        "/api/v1/memory", json={"content": "User's name is Fehri"}, headers=headers
    )
    assert create_resp.status_code == 201
    memory_id = create_resp.json()["id"]
    assert create_resp.json()["content"] == "User's name is Fehri"

    list_resp = await client.get("/api/v1/memory", headers=headers)
    assert list_resp.status_code == 200
    assert [m["id"] for m in list_resp.json()] == [memory_id]

    delete_resp = await client.delete(f"/api/v1/memory/{memory_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp_after = await client.get("/api/v1/memory", headers=headers)
    assert list_resp_after.json() == []


async def test_delete_unknown_memory_returns_404(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.delete(
        "/api/v1/memory/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert resp.status_code == 404


async def test_cannot_delete_another_tenants_memory(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@memtest.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@memtest.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    create_resp = await client.post(
        "/api/v1/memory", json={"content": "A secret only tenant A should see"}, headers=headers_a
    )
    memory_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/memory/{memory_id}", headers=headers_b)
    assert delete_resp.status_code == 404

    list_resp = await client.get("/api/v1/memory", headers=headers_a)
    assert len(list_resp.json()) == 1


async def test_memory_settings_default_enabled_and_toggle(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    get_resp = await client.get("/api/v1/memory/settings", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json() == {"memory_enabled": True}

    patch_resp = await client.patch(
        "/api/v1/memory/settings", json={"enabled": False}, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json() == {"memory_enabled": False}

    get_resp_after = await client.get("/api/v1/memory/settings", headers=headers)
    assert get_resp_after.json() == {"memory_enabled": False}


async def test_chat_with_mock_provider_creates_no_memories(client):
    """MockProvider.generate() just echoes "Mock response to: <prompt>", not the valid JSON
    {"memories": [...], "notes": [...]} object extraction expects — confirms the background task
    degrades gracefully (no rows, no crash) rather than assuming extraction works under a
    provider that can't actually do it."""
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/chat",
        json={"message": "Nama saya Fehri, saya sedang membangun Krixil AI."},
        headers=headers,
    )
    assert resp.status_code == 200

    list_resp = await client.get("/api/v1/memory", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json() == []


async def test_build_memory_context_none_when_empty_or_disabled(client, session_factory):
    registered = await register(client)
    tenant_ctx = TenantContext(
        tenant_id=uuid.UUID(registered["tenant"]["id"]),
        user_id=uuid.UUID(registered["user"]["id"]),
        role=registered["user"]["role"],
        permissions=["*"],
    )

    async with session_factory() as session:
        # No memories yet.
        assert await build_memory_context(session, tenant_ctx) is None

    await client.post(
        "/api/v1/memory",
        json={"content": "User prefers concise answers"},
        headers=auth_headers(registered["access_token"]),
    )

    async with session_factory() as session:
        message = await build_memory_context(session, tenant_ctx)
        assert message is not None
        assert message.role == "system"
        assert "User prefers concise answers" in message.content

    await client.patch(
        "/api/v1/memory/settings",
        json={"enabled": False},
        headers=auth_headers(registered["access_token"]),
    )

    async with session_factory() as session:
        assert await build_memory_context(session, tenant_ctx) is None
