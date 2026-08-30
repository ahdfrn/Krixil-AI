from httpx import AsyncClient


async def register(
    client: AsyncClient,
    tenant_name: str = "Acme Inc",
    email: str = "owner@acme.dev",
    password: str = "correct-horse-battery",
) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"tenant_name": tenant_name, "email": email, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
