from tests.helpers import register


async def test_register_creates_tenant_and_owner_user(client):
    body = await register(client)

    assert body["access_token"]
    assert body["user"]["email"] == "owner@acme.dev"
    assert body["user"]["role"] == "owner"
    assert body["tenant"]["name"] == "Acme Inc"
    assert body["tenant"]["slug"].startswith("acme-inc-")


async def test_login_with_correct_credentials_succeeds(client):
    registered = await register(client)
    tenant_slug = registered["tenant"]["slug"]

    resp = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant_slug, "email": "owner@acme.dev", "password": "correct-horse-battery"},
    )

    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_with_wrong_password_is_rejected(client):
    registered = await register(client)
    tenant_slug = registered["tenant"]["slug"]

    resp = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant_slug, "email": "owner@acme.dev", "password": "wrong-password"},
    )

    assert resp.status_code == 401


async def test_login_with_unknown_tenant_is_rejected(client):
    await register(client)

    resp = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "does-not-exist", "email": "owner@acme.dev", "password": "correct-horse-battery"},
    )

    assert resp.status_code == 401


async def test_chat_endpoint_requires_authentication(client):
    resp = await client.post("/api/v1/chat", json={"message": "hi"})
    assert resp.status_code == 401
