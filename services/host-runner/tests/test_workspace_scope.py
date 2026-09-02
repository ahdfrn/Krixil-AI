from urllib.parse import quote
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def setup(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    a, b = tmp_path / "project-a", tmp_path / "project-b"
    for folder in (legacy, a, b):
        folder.mkdir()
        (folder / "name.txt").write_text(folder.name)
    monkeypatch.setenv("HOST_ROOT", str(legacy))
    monkeypatch.setenv("HOST_RUNNER_API_KEY", "test-key")
    return a, b


def scoped(root):
    return TestClient(
        app,
        headers={
            "X-Krixil-Host-Key": "test-key",
            "X-Krixil-Workspace": quote(str(root), safe=""),
        },
    )


def test_requires_auth_even_for_legacy_files(setup):
    assert TestClient(app).get("/files").status_code == 401
    assert TestClient(app).get("/workspace").status_code == 401


def test_missing_server_key_fails_closed(setup, monkeypatch):
    monkeypatch.delenv("HOST_RUNNER_API_KEY")
    assert scoped(setup[0]).get("/files").status_code == 401


@pytest.mark.asyncio
async def test_concurrent_requests_keep_separate_roots(setup):
    import asyncio
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def read(root):
            response = await client.get(
                "/files/content",
                params={"path": "name.txt"},
                headers={
                    "X-Krixil-Host-Key": "test-key",
                    "X-Krixil-Workspace": quote(str(root), safe=""),
                },
            )
            return response.json()["content"]

        assert await asyncio.gather(read(setup[0]), read(setup[1]), read(setup[0])) == [
            "project-a",
            "project-b",
            "project-a",
        ]


def test_select_outside_legacy_and_keep_sessions_separate(setup):
    a, b = setup
    ca, cb = scoped(a), scoped(b)
    assert ca.get("/workspace").json()["root"] == str(a.resolve())
    for client, name in ((ca, "project-a"), (cb, "project-b"), (ca, "project-a")):
        assert (
            client.get("/files/content", params={"path": "name.txt"}).json()["content"]
            == name
        )


def test_reject_escape_absolute_and_traversal_for_every_operation(setup):
    a, b = setup
    client = scoped(a)
    for path in (str(b / "name.txt"), "../project-b/name.txt"):
        assert client.get("/files/content", params={"path": path}).status_code == 400
        assert (
            client.post("/files", json={"path": path, "content": "changed"}).status_code
            == 400
        )
        assert client.delete("/files", params={"path": path}).status_code == 400
    assert (
        client.post(
            "/run", json={"directory": str(b), "command": "echo test"}
        ).status_code
        == 400
    )
    assert (b / "name.txt").read_text() == "project-b"


def test_reject_broad_missing_and_relative_roots(setup):
    a, _ = setup
    for root in (Path(a.anchor), Path.home(), a / "missing", "relative"):
        assert scoped(root).get("/workspace").status_code == 400


def test_symlink_outside_is_not_read_or_indexed(setup):
    a, b = setup
    try:
        (a / "link.txt").symlink_to(b / "name.txt")
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or elevation")
    client = scoped(a)
    assert client.get("/files/content", params={"path": "link.txt"}).status_code == 400
    assert all(f["path"] != "link.txt" for f in client.get("/index-files").json())
    assert client.get("/search", params={"pattern": "project-b"}).json() == []
