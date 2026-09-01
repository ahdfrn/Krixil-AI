from krixil_cli.goal import build_goal, dir_from_cwd


def test_build_goal_at_root():
    text = build_goal("fix the bug", ".")
    assert text.startswith("Using your host.list_files")
    assert "work in the real folder on this machine" in text
    assert text.endswith("Task: fix the bug")


def test_build_goal_in_subfolder():
    text = build_goal("fix the bug", "demo/app")
    assert '"demo/app" folder' in text
    assert "demo/app/" in text
    assert "cd demo/app &&" in text
    assert text.endswith("Task: fix the bug")


def test_dir_from_cwd_at_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert dir_from_cwd(str(tmp_path)) == "."


def test_dir_from_cwd_in_subfolder(tmp_path, monkeypatch):
    sub = tmp_path / "demo" / "app"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert dir_from_cwd(str(tmp_path)) == "demo/app"


def test_dir_from_cwd_outside_host_root_falls_back_to_root(tmp_path, monkeypatch):
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    unrelated_root = tmp_path / "host-root-does-not-contain-cwd"
    unrelated_root.mkdir()
    assert dir_from_cwd(str(unrelated_root)) == "."
