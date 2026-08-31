"""Real Windows filesystem I/O under HOST_ROOT — no per-tenant isolation, no sandbox. Every path
a client sends is relative to HOST_ROOT (matching services/ai-service's workspace convention, for
symmetry with the frontend); resolve_host_path() is the one place that resolves it and rejects
anything that would escape HOST_ROOT — that confinement is the only safety rail this service has
left, since everything inside HOST_ROOT is otherwise fully readable/writable/executable with no
approval step. See docs/architecture/coding-agent.md ("Real host-folder access")."""

import os
from pathlib import Path

MAX_READ_BYTES = 1_000_000


class HostPathError(ValueError):
    """A requested path resolves outside HOST_ROOT."""


def host_root() -> Path:
    return Path(os.environ["HOST_ROOT"]).resolve()


def resolve_host_path(relative_path: str) -> Path:
    root = host_root()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise HostPathError(f"'{relative_path}' is outside HOST_ROOT ({root})")
    return candidate


def list_files(relative_dir: str = ".") -> list[dict]:
    root = host_root()
    target = resolve_host_path(relative_dir)
    if not target.exists():
        return []
    entries = []
    for path in sorted(target.iterdir()):
        try:
            is_dir = path.is_dir()
            size = path.stat().st_size if not is_dir else None
        except OSError:
            # Windows system/junction entries (e.g. "System Volume Information") can be
            # unreadable even to an admin-less process — skip rather than 500 the whole listing.
            continue
        entries.append(
            {
                "name": path.name,
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "is_dir": is_dir,
                "size_bytes": size,
            }
        )
    return entries


def read_file(relative_path: str) -> str:
    target = resolve_host_path(relative_path)
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"'{relative_path}' is too large to read (max {MAX_READ_BYTES} bytes)")
    return target.read_text(encoding="utf-8", errors="replace")


def write_file(relative_path: str, content: str) -> None:
    target = resolve_host_path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def delete_file(relative_path: str) -> None:
    target = resolve_host_path(relative_path)
    if target.is_dir():
        raise IsADirectoryError(relative_path)
    target.unlink(missing_ok=True)
