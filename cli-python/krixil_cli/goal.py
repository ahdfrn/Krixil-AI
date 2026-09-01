"""Builds the same advisory goal-framing shape apps/web/.../code/page.tsx's buildCodeGoal()
uses — always the host.* tools (real, unsandboxed access), scoped to whichever folder this CLI is
launched from. Keeping the exact phrasing in sync matters less here than on the web (nothing
parses a CLI-submitted goal back apart the way lib/utils/code-sessions.ts's parseCodeGoal() does
for the sidebar), but the shape is copied anyway for consistency and because it's already proven
to work well with the model.
"""

from __future__ import annotations

from pathlib import Path

TOOLS = "host.list_files, host.read_file, host.write_file, host.run_command"


def build_goal(instruction: str, dir_: str) -> str:
    if dir_ == ".":
        return (
            f"Using your {TOOLS} tools, work in the real folder on this machine. "
            f"Task: {instruction}"
        )
    return (
        f'Using your {TOOLS} tools, work within the "{dir_}" folder of the real folder on this '
        f'machine. File paths are relative to the root, so prefix paths with "{dir_}/" (e.g. '
        f'"{dir_}/main.py"). For shell commands that need to run inside that folder, start with '
        f"`cd {dir_} &&`. Task: {instruction}"
    )


def dir_from_cwd(host_root: str) -> str:
    """The folder this CLI was launched from, expressed relative to host_root the same way the
    web app's Code page addresses one — "." if launched at host_root itself, a forward-slash
    relative path otherwise, or "." (with a caller-visible warning, not raised here) if launched
    somewhere outside host_root entirely, since host.* tools can't reach there regardless of what
    this function returns."""
    try:
        relative = Path.cwd().resolve().relative_to(Path(host_root).resolve())
    except ValueError:
        return "."
    return "." if str(relative) == "." else relative.as_posix()
