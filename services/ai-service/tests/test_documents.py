from app.core.config import get_settings
from tests.helpers import auth_headers, register


async def test_upload_txt_document_creates_ready_document(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {
        "file": (
            "notes.txt",
            b"Krixil AI is a self-hosted, multi-tenant AI platform.",
            "text/plain",
        )
    }
    resp = await client.post("/api/v1/documents", files=files, headers=headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "notes.txt"
    assert body["status"] == "ready"
    assert body["chunk_count"] >= 1


async def test_upload_rejects_unsupported_extension(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("virus.exe", b"whatever", "application/octet-stream")}
    resp = await client.post("/api/v1/documents", files=files, headers=headers)

    assert resp.status_code == 400


async def test_upload_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_document_size_mb", 0)
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"just a few bytes", "text/plain")}
    resp = await client.post("/api/v1/documents", files=files, headers=headers)

    assert resp.status_code == 413


async def test_upload_with_no_extractable_text_is_marked_failed(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("empty.txt", b"   \n\n   ", "text/plain")}
    resp = await client.post("/api/v1/documents", files=files, headers=headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert body["chunk_count"] == 0


async def test_list_documents_is_scoped_per_tenant(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@ragdocs.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@ragdocs.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    files = {"file": ("notes.txt", b"tenant a's private document content", "text/plain")}
    await client.post("/api/v1/documents", files=files, headers=headers_a)

    list_a = await client.get("/api/v1/documents", headers=headers_a)
    list_b = await client.get("/api/v1/documents", headers=headers_b)

    assert len(list_a.json()) == 1
    assert list_b.json() == []


async def test_delete_document_removes_it(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    files = {"file": ("notes.txt", b"some content to delete later on", "text/plain")}
    upload_resp = await client.post("/api/v1/documents", files=files, headers=headers)
    document_id = upload_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/documents/{document_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp = await client.get("/api/v1/documents", headers=headers)
    assert list_resp.json() == []


async def test_delete_unknown_document_returns_404(client):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])

    resp = await client.delete(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert resp.status_code == 404


async def test_cannot_delete_another_tenants_document(client):
    tenant_a = await register(client, tenant_name="Tenant A", email="a@ragdelete.dev")
    tenant_b = await register(client, tenant_name="Tenant B", email="b@ragdelete.dev")
    headers_a = auth_headers(tenant_a["access_token"])
    headers_b = auth_headers(tenant_b["access_token"])

    files = {"file": ("notes.txt", b"tenant a's document that b should not delete", "text/plain")}
    upload_resp = await client.post("/api/v1/documents", files=files, headers=headers_a)
    document_id = upload_resp.json()["id"]

    resp = await client.delete(f"/api/v1/documents/{document_id}", headers=headers_b)
    assert resp.status_code == 404
