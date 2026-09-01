"""Credentials + local preferences for the CLI, stored once via `krixil login` so day-to-day use
doesn't need an env file — deliberately different from training/'s .env-based service-account
login (this is a personal, interactive tool, not an unattended one). Still falls back to
KRIXIL_TENANT_SLUG/KRIXIL_EMAIL/KRIXIL_PASSWORD env vars if present and no stored session exists,
matching training/client.py's convention, so the same credentials work either way.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".krixil"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"


@dataclass
class Session:
    base_url: str
    tenant_slug: str
    access_token: str
    # The real, unsandboxed folder host.* tools operate under on the api service's machine (see
    # services/host-runner/.env's HOST_ROOT) — asked once at login so the CLI can compute a goal's
    # `dir` from wherever it's actually launched, the same "operates in the folder you're
    # standing in" feel a real terminal coding agent has. Not enforced client-side; the real
    # boundary is still host-runner's own path confinement.
    host_root: str


def load_session() -> Session | None:
    if not CREDENTIALS_PATH.exists():
        return None
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        return Session(**data)
    except (json.JSONDecodeError, TypeError):
        return None


def save_session(session: Session) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    CREDENTIALS_PATH.write_text(json.dumps(asdict(session), indent=2), encoding="utf-8")
    # Best-effort — Windows ACLs don't honor chmod the way POSIX does, but this is still the
    # correct call on any POSIX machine this CLI runs on, and harmless where it's a no-op.
    try:
        CREDENTIALS_PATH.chmod(0o600)
    except OSError:
        pass


def clear_session() -> None:
    CREDENTIALS_PATH.unlink(missing_ok=True)


def env_login() -> tuple[str, str, str] | None:
    """(tenant_slug, email, password) from the environment, for scripted/non-interactive use —
    same three variables training/client.py already reads, so one .env works for both."""
    slug = os.environ.get("KRIXIL_TENANT_SLUG")
    email = os.environ.get("KRIXIL_EMAIL")
    password = os.environ.get("KRIXIL_PASSWORD")
    if slug and email and password:
        return slug, email, password
    return None
