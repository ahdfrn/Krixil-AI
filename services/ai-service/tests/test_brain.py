import httpx
import respx

from app.core.config import Settings
from tests.helpers import auth_headers, register


def _override_host_runner(monkeypatch, url: str = "http://host-runner.test"):
    monkeypatch.setattr("app.brain.service.get_settings", lambda: Settings(host_runner_url=url))


async def test_brain_status_is_null_before_any_index_run(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.get("/api/v1/brain/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json() is None


async def test_brain_index_walks_real_files_and_stores_real_chunks(client, monkeypatch):
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/index-files").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"path": "app.py", "content": "def handler():\n    return 1\n"},
                    {"path": "README.md", "content": "# Demo\n\nSome docs.\n"},
                ],
            )
        )
        index_resp = await client.post(
            "/api/v1/brain/index", json={"directory": "."}, headers=headers
        )
        assert index_resp.status_code == 200
        assert index_resp.json()["status"] == "running"

    status_resp = await client.get("/api/v1/brain/status", headers=headers)
    body = status_resp.json()
    assert body["status"] == "completed"
    assert body["file_count"] == 2
    assert body["symbol_count"] == 1  # real: app.py's one real function, README.md has none
    assert body["chunk_count"] == 2  # two small files, one chunk each
    assert body["directory"] == "."


async def test_brain_index_is_a_fresh_full_reindex_not_incremental(client, monkeypatch):
    """A second real index run replaces the first tenant's chunks outright — the chunk_count on
    the second run reflects only what the second run actually found, not a cumulative total."""
    _override_host_runner(monkeypatch)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/index-files").mock(
            return_value=httpx.Response(
                200, json=[{"path": "a.py", "content": "def a():\n    pass\n"}]
            )
        )
        await client.post("/api/v1/brain/index", json={"directory": "."}, headers=headers)

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/index-files").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"path": "b.py", "content": "def b():\n    pass\n"},
                    {"path": "c.py", "content": "def c():\n    pass\n"},
                ],
            )
        )
        await client.post("/api/v1/brain/index", json={"directory": "."}, headers=headers)

    status_resp = await client.get("/api/v1/brain/status", headers=headers)
    body = status_resp.json()
    assert body["file_count"] == 2
    assert body["chunk_count"] == 2


async def test_brain_index_fails_honestly_when_host_runner_is_unreachable(client, monkeypatch):
    _override_host_runner(monkeypatch, url="http://127.0.0.1:1")  # nothing listens here
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    await client.post("/api/v1/brain/index", json={"directory": "."}, headers=headers)

    status_resp = await client.get("/api/v1/brain/status", headers=headers)
    body = status_resp.json()
    assert body["status"] == "failed"
    assert "host-runner isn't reachable" in body["error_message"]


async def test_brain_status_is_tenant_scoped(client, monkeypatch):
    _override_host_runner(monkeypatch)
    tenant_a = await register(client, tenant_name="Brain Tenant A", email="a@brain.dev")
    tenant_b = await register(client, tenant_name="Brain Tenant B", email="b@brain.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://host-runner.test/index-files").mock(
            return_value=httpx.Response(
                200, json=[{"path": "a.py", "content": "def a():\n    pass\n"}]
            )
        )
        await client.post("/api/v1/brain/index", json={"directory": "."}, headers=headers_a)

    status_b = await client.get("/api/v1/brain/status", headers=headers_b)
    assert status_b.json() is None


# POST /brain/search deliberately has no offline test here — its real query uses pgvector's
# `<=>` cosine-distance operator (app/db/vector_type.py), which is Postgres-only; empirically
# confirmed it fails to even compile against the SQLite test engine ("near '>': syntax error"),
# not just "returns no rows". Same real limitation app/rag/search.py's own vector/hybrid search
# already has zero offline coverage for — verified against the real Docker stack instead (see
# docs/architecture/kirxil-cli-prd.md's §13 status note).
