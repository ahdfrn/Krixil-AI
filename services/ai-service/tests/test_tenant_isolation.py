from tests.helpers import auth_headers, register


async def test_tenant_cannot_read_another_tenants_conversation(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@tenanta.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@tenantb.dev")

    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    chat_resp = await client.post(
        "/api/v1/chat", json={"message": "tenant A secret"}, headers=headers_a
    )
    conversation_id = chat_resp.json()["conversation_id"]

    # Tenant B cannot see it in their list.
    list_resp = await client.get("/api/v1/conversations", headers=headers_b)
    assert list_resp.json() == []

    # Tenant B cannot fetch it directly — 404, not 403, so existence isn't leaked either.
    get_resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers_b)
    assert get_resp.status_code == 404

    # Tenant B cannot hijack it via the chat endpoint.
    hijack_resp = await client.post(
        "/api/v1/chat",
        json={"message": "hijack", "conversation_id": conversation_id},
        headers=headers_b,
    )
    assert hijack_resp.status_code == 404

    # Tenant A can still read their own conversation, untouched.
    own_resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers_a)
    assert own_resp.status_code == 200
    assert len(own_resp.json()["messages"]) == 2


async def test_same_email_can_own_separate_tenants(client):
    tenant_a = await register(client, tenant_name="Company A", email="same@shared.dev")
    tenant_b = await register(client, tenant_name="Company B", email="same@shared.dev")

    assert tenant_a["tenant"]["id"] != tenant_b["tenant"]["id"]
    assert tenant_a["access_token"] != tenant_b["access_token"]
