"""Renders an agent run's steps as a live terminal transcript — a direct Python port of
apps/web/src/components/agent-run/step-view.tsx's "⏺ Tool(args)" / "⎿ result" shape, so the CLI
and the web app read identically. Kept as pure functions returning rich renderables rather than
printing directly, so repl.py can feed them into a single rich.live.Live that redraws in place as
polling delivers new steps.
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

FILE_TOOLS = {"host.list_files"}
READ_TOOLS = {"host.read_file"}
WRITE_TOOLS = {"host.write_file"}
RUN_TOOLS = {"host.run_command"}
MAX_LISTED_ENTRIES = 20
MAX_OUTPUT_LINES = 40  # A terminal has no click-to-expand — trimmed instead, not collapsed.


def _summarize_tool_call(tool_name: str | None, args: dict[str, Any]) -> str:
    path = args.get("path")
    command = args.get("command")
    directory = args.get("directory")

    if tool_name in FILE_TOOLS:
        return f"List({path if path and path != '.' else '.'})"
    if tool_name in READ_TOOLS:
        return f"Read({path or '?'})"
    if tool_name in WRITE_TOOLS:
        return f"Write({path or '?'})"
    if tool_name in RUN_TOOLS:
        return (
            f"Bash(cd {directory} && {command})"
            if directory and directory != "."
            else f"Bash({command})"
        )
    return tool_name or "Tool call"


def _trim(lines: list[str]) -> list[str]:
    if len(lines) <= MAX_OUTPUT_LINES:
        return lines
    return [*lines[:MAX_OUTPUT_LINES], f"… and {len(lines) - MAX_OUTPUT_LINES} more lines"]


def _result_lines(summary: str, body_lines: list[str], color: str) -> list[Text]:
    out = [Text.from_markup(f"  [dim]⎿[/dim] [{color}]{summary}[/{color}]")]
    for line in _trim(body_lines):
        out.append(Text(f"     {line}", style="dim"))
    return out


def render_step(step: dict[str, Any]) -> list[Text]:
    step_type = step["type"]

    if step_type == "tool_call":
        summary = _summarize_tool_call(step.get("tool_name"), step["content"].get("arguments", {}))
        return [Text.from_markup(f"[bold cyan]⏺[/bold cyan] {summary}")]

    if step_type == "observation":
        content = step["content"]
        tool_name = step.get("tool_name")

        if content.get("status") == "pending_approval":
            return _result_lines("Paused for approval", [], "yellow")
        if "error" in content:
            return _result_lines("Error", [str(content["error"])], "red")

        if tool_name in FILE_TOOLS:
            entries = content.get("entries", [])
            if not entries:
                return _result_lines("No files here", [], "white")
            shown = entries[:MAX_LISTED_ENTRIES]
            lines = [f"{'/' if e['is_dir'] else ''}{e['name']}" for e in shown]
            if len(entries) > len(shown):
                lines.append(f"…and {len(entries) - len(shown)} more")
            return _result_lines(f"Listed {len(entries)} paths", lines, "white")

        if tool_name in READ_TOOLS:
            text = content.get("content", "")
            return _result_lines(f"Read {len(text.splitlines())} lines", text.splitlines(), "white")

        if tool_name in WRITE_TOOLS:
            return _result_lines("Saved", [], "green")

        if tool_name in RUN_TOOLS:
            exit_code = content.get("exit_code")
            timed_out = content.get("timed_out") is True
            ok = exit_code == 0 and not timed_out
            summary = "Timed out" if timed_out else f"Exit {exit_code}"
            body = [
                *(content.get("stdout") or "").splitlines(),
                *(content.get("stderr") or "").splitlines(),
            ]
            return _result_lines(summary, body, "green" if ok else "red")

        return _result_lines("Result", [str(content)], "white")

    # final_response
    return [Text(""), Text(str(step["content"].get("content", "")))]


def render_transcript(
    goal: str, steps: list[dict[str, Any]], status: str, elapsed_seconds: float
) -> Group:
    lines: list[Text] = [Text.from_markup(f"[bold]›[/bold] {goal}"), Text("")]
    for step in steps:
        lines.extend(render_step(step))
    if status == "running":
        tool_calls = sum(1 for s in steps if s["type"] == "tool_call")
        lines.append(
            Text.from_markup(
                f"[cyan]●[/cyan] Working… ({int(elapsed_seconds)}s · {tool_calls} tool calls) "
                "[dim](Ctrl+C to stop)[/dim]"
            )
        )
    elif status == "cancelled":
        lines.append(Text("Stopped.", style="dim"))
    elif status == "waiting_approval":
        lines.append(
            Text(
                "Paused waiting on approval — resolve it from the web app's Agents page.",
                style="yellow",
            )
        )
    elif status == "failed":
        lines.append(Text("Failed.", style="red"))
    return Group(*lines)
