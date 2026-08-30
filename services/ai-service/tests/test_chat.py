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
        "/api/v1/chat", json={"message": "again", "conversation_id": conversation_id}, headers=headers
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
                events.append(json.loads(line[len("data: "):]))

    types = [e["type"] for e in events]
    assert types[0] == "conversation"
    assert "chunk" in types
    assert types[-1] == "done"

    conversation_id = events[0]["conversation_id"]
    detail_resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["messages"]) == 2
