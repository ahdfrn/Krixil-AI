"""Real, narrow, heuristic BLOCK-tier classification for run_command-shaped tools (the PRD's own
"CRITICAL → BLOCK" example: `rm -rf /`). Layered on top of the existing HIGH/MEDIUM approval tiers
(app/tools/base.py's APPROVAL_REQUIRED_LEVELS) — not a replacement for them, and deliberately
scoped much narrower than "anything destructive." The PRD's own examples draw this line
explicitly: `rm -rf /` gets BLOCKed outright (no legitimate use case in an agent coding session,
so no amount of human approval should offer a "yes"), while `DROP DATABASE production` only
REQUIRES CONFIRMATION — that's already the existing HIGH-risk approval pause, not something this
module escalates further. This list only contains the former kind: whole-filesystem/whole-disk
wipes with no plausible legitimate use here.

This is a hard-coded pattern list, not intent understanding — a determined or oddly-phrased
command can slip past it (e.g. `rm -rf /` split across a shell variable), and that's an accepted,
documented trade-off, not a bug to chase indefinitely. It's a backstop against catastrophic
accidents (a model confidently issuing a command it shouldn't), not a security boundary — real
security is host-runner having full native access at all (see docs/architecture/coding-agent.md's
"Real host-folder access") and the human-approval gate this sits in front of. Extend the pattern
list below as real incidents or reports turn up, not preemptively.
"""

import re

_BLOCK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\brm\s+(-[a-z]*r[a-z]*f[a-z]*|-[a-z]*f[a-z]*r[a-z]*|--recursive\s+--force"
            r"|--force\s+--recursive)\s+(/|/\*|~|--no-preserve-root)(\s|$)",
            re.IGNORECASE,
        ),
        "recursive force-delete of the filesystem root",
    ),
    (
        re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
        "formatting a whole drive",
    ),
    (
        re.compile(r"\b(rd|rmdir)\s+(/s\s+/q|/q\s+/s)\s+[a-z]:\\?(\s|$)", re.IGNORECASE),
        "recursive delete of a whole drive",
    ),
    (
        re.compile(r"remove-item\b.*-recurse\b.*-force\b\s+[a-z]:\\?(\s|$)", re.IGNORECASE),
        "recursive force-delete of a whole drive",
    ),
    (
        re.compile(r"\bdd\s+.*of=/dev/(sd|hd|nvme|disk)[a-z0-9]*", re.IGNORECASE),
        "writing directly over a disk device",
    ),
    (
        re.compile(r"\bmkfs(\.\w+)?\s+/dev/(sd|hd|nvme|disk)[a-z0-9]*", re.IGNORECASE),
        "reformatting a disk device",
    ),
]


def find_block_reason(command: str) -> str | None:
    """A human-readable reason this command is blocked outright, or None if it isn't. Only ever
    called on a real, already-validated command string — see host_tools.py/code_tools.py's
    HostRunCommandInput/CodeRunCommandInput.command."""
    for pattern, reason in _BLOCK_PATTERNS:
        if pattern.search(command):
            return reason
    return None
