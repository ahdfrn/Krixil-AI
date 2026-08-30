import json

from tests.helpers import auth_headers, register


async def test_chat_happy_path_persists_conversation(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post("/api/v1/chat", json={"message": "hello"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "mock"
    assert "hello" in body["message"]["content"]
    conversation_id = body["conversation_id"]

    # Follow-up in the same conversation.
    resp2 = await client.post(
        "/api/v1/chat",
        json={"message": "again", "conversation_id": conversation_id},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["conversation_id"] == conversation_id

    list_resp = await client.get("/api/v1/conversations", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    detail_resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail_resp.status_code == 200
    messages = detail_resp.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]


async def test_chat_with_unknown_conversation_id_returns_404(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post(
        "/api/v1/chat",
        json={"message": "hi", "conversation_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_rename_conversation_updates_title(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post("/api/v1/chat", json={"message": "hello"}, headers=headers)
    conversation_id = resp.json()["conversation_id"]

    rename_resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Renamed conversation"},
        headers=headers,
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["title"] == "Renamed conversation"

    detail_resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail_resp.json()["title"] == "Renamed conversation"


async def test_rename_unknown_conversation_returns_404(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.patch(
        "/api/v1/conversations/00000000-0000-0000-0000-000000000000",
        json={"title": "New title"},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_cannot_rename_another_tenants_conversation(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@convrename.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@convrename.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    resp = await client.post("/api/v1/chat", json={"message": "hello"}, headers=headers_a)
    conversation_id = resp.json()["conversation_id"]

    rename_resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Hijacked"},
        headers=headers_b,
    )
    assert rename_resp.status_code == 404


async def test_delete_conversation_removes_it_and_its_messages(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.post("/api/v1/chat", json={"message": "hello"}, headers=headers)
    conversation_id = resp.json()["conversation_id"]

    delete_resp = await client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp = await client.get("/api/v1/conversations", headers=headers)
    assert list_resp.json() == []

    detail_resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail_resp.status_code == 404


async def test_delete_unknown_conversation_returns_404(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.delete(
        "/api/v1/conversations/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert resp.status_code == 404


async def test_cannot_delete_another_tenants_conversation(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@convdelete.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@convdelete.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    resp = await client.post("/api/v1/chat", json={"message": "hello"}, headers=headers_a)
    conversation_id = resp.json()["conversation_id"]

    delete_resp = await client.delete(
        f"/api/v1/conversations/{conversation_id}", headers=headers_b
    )
    assert delete_resp.status_code == 404

    # Still there for tenant A, untouched by tenant B's failed attempt.
    list_resp = await client.get("/api/v1/conversations", headers=headers_a)
    assert len(list_resp.json()) == 1


async def test_chat_stream_emits_conversation_chunks_and_done(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    events = []
    async with client.stream(
        "POST", "/api/v1/chat/stream", json={"message": "hi"}, headers=headers
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))

    types = [e["type"] for e in events]
    assert types[0] == "conversation"
    assert "chunk" in types
    assert types[-1] == "done"

    conversation_id = events[0]["conversation_id"]
    detail_resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["messages"]) == 2
