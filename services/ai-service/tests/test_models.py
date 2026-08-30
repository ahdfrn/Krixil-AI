from tests.helpers import auth_headers, register


async def test_list_models_returns_the_one_real_model(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.get("/api/v1/models", headers=headers)
    assert resp.status_code == 200
    models = resp.json()
    assert len(models) == 1
    assert models[0]["id"] == "auto"
    assert models[0]["name"] == "Krixil Auto"


async def test_list_models_requires_auth(client):
    resp = await client.get("/api/v1/models")
    assert resp.status_code == 401
