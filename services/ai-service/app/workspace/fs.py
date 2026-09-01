"""Filesystem operations for a tenant's coding workspace. Every tenant gets its own directory
under settings.workspace_root; this module is the single place that resolves a client-supplied
relative path against that directory and rejects anything that would escape it — every caller
(the code.* tools and the workspace router) goes through resolve_workspace_path() rather than
touching Path objects directly, so the traversal check can't be accidentally bypassed."""

import os
import re
import uuid
from pathlib import Path

from app.core.config import get_settings

MAX_READ_BYTES = 1_000_000  # Plenty for source files; guards against pulling something huge into
# an LLM's context via code.read_file.
MAX_SEARCH_RESULTS = 200
MAX_SEARCH_FILE_BYTES = 2_000_000
SEARCH_IGNORED_DIR_NAMES = {"node_modules", "__pycache__", "venv", "dist", "build", ".next"}


class WorkspacePathError(ValueError):
    """A requested path resolves outside the tenant's own workspace directory."""


def tenant_workspace_root(tenant_id: uuid.UUID) -> Path:
    root = (Path(get_settings().workspace_root) / str(tenant_id)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_workspace_path(tenant_id: uuid.UUID, relative_path: str) -> Path:
    root = tenant_workspace_root(tenant_id)
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise WorkspacePathError(f"'{relative_path}' is outside the workspace")
    return candidate


def list_files(tenant_id: uuid.UUID, relative_dir: str = ".") -> list[dict]:
    root = tenant_workspace_root(tenant_id)
    target = resolve_workspace_path(tenant_id, relative_dir)
    if not target.exists():
        return []
    entries = []
    for path in sorted(target.iterdir()):
        entries.append(
            {
                "name": path.name,
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "is_dir": path.is_dir(),
                "size_bytes": path.stat().st_size if path.is_file() else None,
            }
        )
    return entries


def read_file(tenant_id: uuid.UUID, relative_path: str) -> str:
    target = resolve_workspace_path(tenant_id, relative_path)
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"'{relative_path}' is too large to read (max {MAX_READ_BYTES} bytes)")
    return target.read_text(encoding="utf-8", errors="replace")


def write_file(tenant_id: uuid.UUID, relative_path: str, content: str) -> None:
    target = resolve_workspace_path(tenant_id, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def delete_file(tenant_id: uuid.UUID, relative_path: str) -> None:
    target = resolve_workspace_path(tenant_id, relative_path)
    if target.is_dir():
        raise IsADirectoryError(relative_path)
    target.unlink(missing_ok=True)


def search_files(tenant_id: uuid.UUID, pattern: str, relative_dir: str = ".") -> list[dict]:
    """Same approach as services/host-runner/app/fs.py's search_files (not shared code — these
    are two separate deployable services, one in-process here, one a standalone native process —
    but the same reasoning applies): a real recursive regex search over stdlib-only I/O, not a
    shell-out to ripgrep, so it works the same regardless of what's installed in the sandbox
    image. Capped result count, binary files skipped by UTF-8 decode failure, common
    dependency/build directories and dotdirs never walked into."""
    root = tenant_workspace_root(tenant_id)
    target = resolve_workspace_path(tenant_id, relative_dir)
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid search pattern: {exc}") from exc

    results: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [
            d for d in dirnames if d not in SEARCH_IGNORED_DIR_NAMES and not d.startswith(".")
        ]
        for filename in sorted(filenames):
            file_path = Path(dirpath) / filename
            try:
                if file_path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                    continue
                text = file_path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    results.append(
                        {
                            "path": str(file_path.relative_to(root)).replace("\\", "/"),
                            "line_number": line_number,
                            "line": line.strip()[:300],
                        }
                    )
                    if len(results) >= MAX_SEARCH_RESULTS:
                        return results
    return results
