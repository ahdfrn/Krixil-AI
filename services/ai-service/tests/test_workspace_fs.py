import uuid

import pytest

from app.workspace.fs import (
    WorkspacePathError,
    delete_file,
    list_files,
    read_file,
    resolve_workspace_path,
    write_file,
)


@pytest.fixture(autouse=True)
def _workspace_root(tmp_path, monkeypatch):
    from app.core.config import Settings

    monkeypatch.setattr(
        "app.workspace.fs.get_settings", lambda: Settings(workspace_root=str(tmp_path))
    )


def test_write_then_read_round_trips():
    tenant_id = uuid.uuid4()
    write_file(tenant_id, "hello.py", "print('hi')\n")
    assert read_file(tenant_id, "hello.py") == "print('hi')\n"


def test_write_creates_parent_directories():
    tenant_id = uuid.uuid4()
    write_file(tenant_id, "src/nested/app.py", "x = 1\n")
    assert read_file(tenant_id, "src/nested/app.py") == "x = 1\n"


def test_list_files_returns_entries_relative_to_workspace():
    tenant_id = uuid.uuid4()
    write_file(tenant_id, "a.py", "")
    write_file(tenant_id, "sub/b.py", "")

    entries = {e["path"]: e for e in list_files(tenant_id)}
    assert "a.py" in entries
    assert entries["a.py"]["is_dir"] is False
    assert "sub" in entries
    assert entries["sub"]["is_dir"] is True


def test_list_files_on_missing_directory_returns_empty():
    assert list_files(uuid.uuid4(), "does/not/exist") == []


def test_delete_removes_file():
    tenant_id = uuid.uuid4()
    write_file(tenant_id, "gone.py", "")
    delete_file(tenant_id, "gone.py")
    assert list_files(tenant_id) == []


def test_delete_missing_file_is_a_no_op():
    delete_file(uuid.uuid4(), "never-existed.py")


def test_delete_rejects_a_directory():
    tenant_id = uuid.uuid4()
    write_file(tenant_id, "sub/b.py", "")
    with pytest.raises(IsADirectoryError):
        delete_file(tenant_id, "sub")


def test_tenants_cannot_read_each_others_files():
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    write_file(tenant_a, "secret.py", "tenant a's data")
    assert list_files(tenant_b) == []
    with pytest.raises(FileNotFoundError):
        read_file(tenant_b, "secret.py")


@pytest.mark.parametrize(
    "traversal_path",
    [
        "../escape.txt",
        "../../etc/passwd",
        "sub/../../escape.txt",
    ],
)
def test_traversal_outside_workspace_is_rejected(traversal_path):
    tenant_id = uuid.uuid4()
    with pytest.raises(WorkspacePathError):
        resolve_workspace_path(tenant_id, traversal_path)


def test_absolute_path_is_confined_to_the_workspace():
    # An absolute path joined onto the workspace root with `/` still resolves *inside* the
    # workspace on POSIX (Path("/root") / "/etc/passwd" == Path("/etc/passwd") is the actual
    # traversal risk) — assert it's caught rather than assuming Path's own join semantics are
    # already safe.
    tenant_id = uuid.uuid4()
    with pytest.raises(WorkspacePathError):
        resolve_workspace_path(tenant_id, "/etc/passwd")
