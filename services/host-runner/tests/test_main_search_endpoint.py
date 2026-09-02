"""GET /search — thin HTTP wrapper over app.fs.search_files (see test_fs_search.py for the real
logic coverage); this just confirms the endpoint wires status codes and the response shape
correctly."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOST_ROOT", str(tmp_path))
    from app.main import app

    return TestClient(app)


def test_search_returns_matches(tmp_path, client):
    (tmp_path / "a.py").write_text("def handler():\n    pass\n", encoding="utf-8")

    resp = client.get("/search", params={"pattern": "handler"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["path"] == "a.py"
    assert body[0]["line_number"] == 1


def test_search_returns_empty_list_for_no_matches(tmp_path, client):
    (tmp_path / "a.py").write_text("nothing interesting\n", encoding="utf-8")

    resp = client.get("/search", params={"pattern": "zzz_no_match_zzz"})

    assert resp.status_code == 200
    assert resp.json() == []


def test_search_rejects_invalid_regex_with_400(client):
    resp = client.get("/search", params={"pattern": "(unclosed"})
    assert resp.status_code == 400
    assert "Invalid search pattern" in resp.json()["detail"]


def test_search_rejects_a_path_outside_host_root(client):
    resp = client.get("/search", params={"pattern": "x", "path": "../outside"})
    assert resp.status_code == 400
    assert "outside HOST_ROOT" in resp.json()["detail"]


def test_index_files_returns_real_path_and_content(tmp_path, client):
    (tmp_path / "a.py").write_text("def handler():\n    pass\n", encoding="utf-8")

    resp = client.get("/index-files")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["path"] == "a.py"
    assert body[0]["content"] == "def handler():\n    pass\n"


def test_index_files_rejects_a_path_outside_host_root(client):
    resp = client.get("/index-files", params={"path": "../outside"})
    assert resp.status_code == 400
    assert "outside HOST_ROOT" in resp.json()["detail"]
