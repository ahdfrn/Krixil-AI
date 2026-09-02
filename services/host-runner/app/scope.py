"""Per-request project root. No mutation of process-wide HOST_ROOT."""

import os
from contextvars import ContextVar
from pathlib import Path

workspace_root: ContextVar[Path | None] = ContextVar("workspace_root", default=None)


def validate_workspace(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("Workspace must be an absolute local directory")
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("Workspace must be a directory")
    # Selecting a project must not accidentally grant an entire drive/profile/system tree.
    protected = {Path(path.anchor), Path.home().resolve()}
    for name in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        if os.environ.get(name):
            protected.add(Path(os.environ[name]).resolve())
    if path in protected or (os.name == "nt" and str(path).startswith("\\\\")):
        raise ValueError(
            "Select a project folder, not a drive, home, system folder, or network share"
        )
    return path
