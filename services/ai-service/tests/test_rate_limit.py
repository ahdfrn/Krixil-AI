from app.core.config import get_settings
from tests.helpers import auth_headers, register


async def test_chat_rate_limit_returns_429_after_exceeding_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_chat_per_minute", 2)

    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    r1 = await client.post("/api/v1/chat", json={"message": "one"}, headers=headers)
    r2 = await client.post("/api/v1/chat", json={"message": "two"}, headers=headers)
    r3 = await client.post("/api/v1/chat", json={"message": "three"}, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


async def test_chat_rate_limit_is_isolated_per_tenant(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_chat_per_minute", 1)

    tenant_a = await register(client, tenant_name="Tenant A", email="a@ratelimit.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@ratelimit.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    r1 = await client.post("/api/v1/chat", json={"message": "hi"}, headers=headers_a)
    r2 = await client.post("/api/v1/chat", json={"message": "hi"}, headers=headers_a)
    r3 = await client.post("/api/v1/chat", json={"message": "hi"}, headers=headers_b)

    assert r1.status_code == 200
    assert r2.status_code == 429
    assert r3.status_code == 200
