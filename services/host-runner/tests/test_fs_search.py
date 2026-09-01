"""First real test suite this service has ever had — added alongside search_files(), the first
piece of logic here non-trivial enough (regex matching, directory walking, binary detection) to
be worth more than eyeballing. Real temp directories, real files, no mocking — fs.py's whole job
is real filesystem I/O."""

import pytest

from app.fs import HostPathError, search_files


@pytest.fixture
def host_root(tmp_path, monkeypatch):
    monkeypatch.setenv("HOST_ROOT", str(tmp_path))
    return tmp_path


def test_finds_a_real_match_with_line_number(host_root):
    (host_root / "app.py").write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")

    results = search_files("divide")

    assert len(results) == 1
    assert results[0]["path"] == "app.py"
    assert results[0]["line_number"] == 1
    assert "divide" in results[0]["line"]


def test_searches_recursively_into_subdirectories(host_root):
    nested = host_root / "src" / "utils"
    nested.mkdir(parents=True)
    (nested / "parse.py").write_text("TODO: handle empty input\n", encoding="utf-8")

    results = search_files("TODO")

    assert len(results) == 1
    assert results[0]["path"] == "src/utils/parse.py"


def test_skips_ignored_directories(host_root):
    ignored = host_root / "node_modules" / "some-pkg"
    ignored.mkdir(parents=True)
    (ignored / "index.js").write_text("const TODO = 1;\n", encoding="utf-8")
    (host_root / "real.js").write_text("const TODO = 2;\n", encoding="utf-8")

    results = search_files("TODO")

    assert [r["path"] for r in results] == ["real.js"]


def test_skips_dot_directories(host_root):
    git_dir = host_root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("TODO inside git internals\n", encoding="utf-8")

    results = search_files("TODO")

    assert results == []


def test_skips_binary_files_instead_of_erroring(host_root):
    (host_root / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02TODO\xff\xfe")
    (host_root / "notes.txt").write_text("TODO write real notes\n", encoding="utf-8")

    results = search_files("TODO")

    assert [r["path"] for r in results] == ["notes.txt"]


def test_scopes_search_to_the_given_subdirectory(host_root):
    (host_root / "a.py").write_text("MARKER\n", encoding="utf-8")
    sub = host_root / "sub"
    sub.mkdir()
    (sub / "b.py").write_text("MARKER\n", encoding="utf-8")

    results = search_files("MARKER", relative_dir="sub")

    assert [r["path"] for r in results] == ["sub/b.py"]


def test_invalid_regex_raises_a_clear_error(host_root):
    with pytest.raises(ValueError, match="Invalid search pattern"):
        search_files("(unclosed")


def test_path_outside_host_root_is_rejected(host_root):
    with pytest.raises(HostPathError):
        search_files("anything", relative_dir="../outside")


def test_caps_results_at_the_documented_limit(host_root, monkeypatch):
    import app.fs as fs_module

    monkeypatch.setattr(fs_module, "MAX_SEARCH_RESULTS", 3)
    (host_root / "many.txt").write_text("\n".join("MATCH" for _ in range(10)), encoding="utf-8")

    results = search_files("MATCH")

    assert len(results) == 3
