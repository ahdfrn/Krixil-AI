from krixil_cli import config
from krixil_cli.config import Session


def _use_tmp_config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / ".krixil")
    monkeypatch.setattr(config, "CREDENTIALS_PATH", tmp_path / ".krixil" / "credentials.json")


def test_load_session_returns_none_when_nothing_saved(tmp_path, monkeypatch):
    _use_tmp_config_dir(tmp_path, monkeypatch)
    assert config.load_session() is None


def test_save_then_load_round_trips(tmp_path, monkeypatch):
    _use_tmp_config_dir(tmp_path, monkeypatch)
    session = Session(
        base_url="http://localhost:8000/api/v1",
        tenant_slug="acme-1",
        access_token="tok-123",
        host_root="D:\\",
    )
    config.save_session(session)
    loaded = config.load_session()
    assert loaded == session


def test_clear_session_removes_the_file(tmp_path, monkeypatch):
    _use_tmp_config_dir(tmp_path, monkeypatch)
    config.save_session(Session(base_url="x", tenant_slug="y", access_token="z", host_root="D:\\"))
    config.clear_session()
    assert config.load_session() is None


def test_env_login_requires_all_three(monkeypatch):
    monkeypatch.delenv("KRIXIL_TENANT_SLUG", raising=False)
    monkeypatch.delenv("KRIXIL_EMAIL", raising=False)
    monkeypatch.delenv("KRIXIL_PASSWORD", raising=False)
    assert config.env_login() is None

    monkeypatch.setenv("KRIXIL_TENANT_SLUG", "acme-1")
    monkeypatch.setenv("KRIXIL_EMAIL", "a@b.dev")
    monkeypatch.setenv("KRIXIL_PASSWORD", "correct-horse-battery")
    assert config.env_login() == ("acme-1", "a@b.dev", "correct-horse-battery")
