"""Real Windows filesystem I/O under HOST_ROOT — no per-tenant isolation, no sandbox. Every path
a client sends is relative to HOST_ROOT (matching services/ai-service's workspace convention, for
symmetry with the frontend); resolve_host_path() is the one place that resolves it and rejects
anything that would escape HOST_ROOT — that confinement is the only safety rail this service has
left, since everything inside HOST_ROOT is otherwise fully readable/writable/executable with no
approval step. See docs/architecture/coding-agent.md ("Real host-folder access")."""

import os
import re
from pathlib import Path
from app.scope import workspace_root

MAX_READ_BYTES = 1_000_000
MAX_SEARCH_RESULTS = 200
# A file this large is almost certainly not something a code search cares about (a bundled
# asset, a data dump, a lockfile) — skipped rather than read in full, same spirit as
# MAX_READ_BYTES above but scoped to search instead of erroring the whole request out.
MAX_SEARCH_FILE_BYTES = 2_000_000
SEARCH_IGNORED_DIR_NAMES = {
    "node_modules",
    "__pycache__",
    "venv",
    "dist",
    "build",
    ".next",
}
# Project Brain indexing (services/ai-service/app/brain/) — a real, bounded cap on how many real
# files one index run reads, so pointing it at a huge tree doesn't turn into an unbounded crawl.
MAX_INDEX_FILES = 500
MAX_INDEX_FILE_BYTES = 500_000


class HostPathError(ValueError):
    """A requested path resolves outside HOST_ROOT."""


def host_root() -> Path:
    selected = workspace_root.get()
    if selected is not None:
        return selected
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
            resolve_host_path(str(path))
            is_dir = path.is_dir()
            size = path.stat().st_size if not is_dir else None
        except (OSError, HostPathError):
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
        raise ValueError(
            f"'{relative_path}' is too large to read (max {MAX_READ_BYTES} bytes)"
        )
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


def search_files(pattern: str, relative_dir: str = ".") -> list[dict]:
    """Real recursive regex search, not a shell-out to ripgrep — this service otherwise has zero
    external binary dependencies (list/read/write/run are all stdlib), and a search tool an agent
    calls mid-run shouldn't start failing just because `rg` isn't on this particular machine's
    PATH (a real, previously-hit problem — see docs/architecture/coding-agent.md's `kirxil
    search` history). Caps results at MAX_SEARCH_RESULTS so one broad pattern over a huge tree
    can't return an unbounded response; skips files it can't decode as UTF-8 text (binary,
    basically) rather than erroring, and common dependency/build directories rather than walking
    into them at all."""
    root = host_root()
    target = resolve_host_path(relative_dir)
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid search pattern: {exc}") from exc

    results: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SEARCH_IGNORED_DIR_NAMES and not d.startswith(".")
        ]
        for filename in sorted(filenames):
            file_path = Path(dirpath) / filename
            try:
                resolve_host_path(str(file_path))
                if file_path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                    continue
                text = file_path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError, HostPathError):
                # Unreadable, or not valid UTF-8 text (the practical definition of "binary" used
                # here) — skip rather than fail the whole search over one file.
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


def walk_indexable_files(relative_dir: str = ".") -> list[dict]:
    """Real recursive walk returning {path, content} for Project Brain indexing
    (services/ai-service/app/brain/service.py) — same ignored-directories/binary-skip logic as
    search_files above, just returning whole file content instead of regex matches. Capped at
    MAX_INDEX_FILES so pointing this at a huge tree stays bounded; files are walked in sorted
    order so which ones get cut off at the cap is at least deterministic, not directory-order
    luck."""
    root = host_root()
    target = resolve_host_path(relative_dir)

    results: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in SEARCH_IGNORED_DIR_NAMES and not d.startswith(".")
        )
        for filename in sorted(filenames):
            file_path = Path(dirpath) / filename
            try:
                resolve_host_path(str(file_path))
                if file_path.stat().st_size > MAX_INDEX_FILE_BYTES:
                    continue
                text = file_path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError, HostPathError):
                continue
            results.append(
                {
                    "path": str(file_path.relative_to(root)).replace("\\", "/"),
                    "content": text,
                }
            )
            if len(results) >= MAX_INDEX_FILES:
                return results
    return results
