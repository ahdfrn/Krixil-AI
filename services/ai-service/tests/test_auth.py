import pyotp

from tests.helpers import auth_headers, register


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
        json={
            "tenant_slug": tenant_slug,
            "email": "owner@acme.dev",
            "password": "correct-horse-battery",
        },
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
        json={
            "tenant_slug": "does-not-exist",
            "email": "owner@acme.dev",
            "password": "correct-horse-battery",
        },
    )

    assert resp.status_code == 401


async def test_chat_endpoint_requires_authentication(client):
    resp = await client.post("/api/v1/chat", json={"message": "hi"})
    assert resp.status_code == 401


async def _enable_2fa(client, headers) -> str:
    """Runs the real setup -> confirm flow and returns the confirmed secret."""
    setup_resp = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    assert setup_resp.status_code == 200
    secret = setup_resp.json()["secret"]
    assert setup_resp.json()["otpauth_url"].startswith("otpauth://totp/")

    code = pyotp.TOTP(secret).now()
    confirm_resp = await client.post(
        "/api/v1/auth/2fa/confirm", json={"code": code}, headers=headers
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["totp_enabled"] is True
    return secret


async def test_2fa_confirm_with_wrong_code_stays_disabled(client):
    registered = await register(client)
    tenant_slug = registered["tenant"]["slug"]
    headers = auth_headers(registered["access_token"])

    setup_resp = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    assert setup_resp.status_code == 200

    confirm_resp = await client.post(
        "/api/v1/auth/2fa/confirm", json={"code": "000000"}, headers=headers
    )
    assert confirm_resp.status_code == 400

    # Still disabled: a normal login with no code succeeds.
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": tenant_slug,
            "email": "owner@acme.dev",
            "password": "correct-horse-battery",
        },
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["user"]["totp_enabled"] is False


async def test_login_after_2fa_enabled_requires_code(client):
    registered = await register(client)
    tenant_slug = registered["tenant"]["slug"]
    headers = auth_headers(registered["access_token"])
    await _enable_2fa(client, headers)

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": tenant_slug,
            "email": "owner@acme.dev",
            "password": "correct-horse-battery",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "2FA code required"


async def test_login_with_wrong_2fa_code_is_rejected(client):
    registered = await register(client)
    tenant_slug = registered["tenant"]["slug"]
    headers = auth_headers(registered["access_token"])
    await _enable_2fa(client, headers)

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": tenant_slug,
            "email": "owner@acme.dev",
            "password": "correct-horse-battery",
            "totp_code": "000000",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid 2FA code"


async def test_login_with_correct_2fa_code_succeeds(client):
    registered = await register(client)
    tenant_slug = registered["tenant"]["slug"]
    headers = auth_headers(registered["access_token"])
    secret = await _enable_2fa(client, headers)

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": tenant_slug,
            "email": "owner@acme.dev",
            "password": "correct-horse-battery",
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert resp.json()["user"]["totp_enabled"] is True


async def test_disable_2fa_requires_valid_code_and_clears_state(client):
    registered = await register(client)
    tenant_slug = registered["tenant"]["slug"]
    headers = auth_headers(registered["access_token"])
    secret = await _enable_2fa(client, headers)

    wrong_resp = await client.post(
        "/api/v1/auth/2fa/disable", json={"code": "000000"}, headers=headers
    )
    assert wrong_resp.status_code == 400

    disable_resp = await client.post(
        "/api/v1/auth/2fa/disable", json={"code": pyotp.TOTP(secret).now()}, headers=headers
    )
    assert disable_resp.status_code == 200
    assert disable_resp.json()["totp_enabled"] is False

    # A normal login with no code succeeds again.
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": tenant_slug,
            "email": "owner@acme.dev",
            "password": "correct-horse-battery",
        },
    )
    assert login_resp.status_code == 200

