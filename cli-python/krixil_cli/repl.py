"""The interactive loop and the single-goal runner both live here — `krixil` drops into the loop,
`krixil run "<goal>"` calls run_goal_live() once and exits, same underlying mechanics either way.
"""

from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live
from rich.prompt import Prompt

from krixil_cli.api import ApiError, KrixilApi, ModelInfo
from krixil_cli.goal import build_goal

POLL_INTERVAL_SECONDS = 1.0


def run_goal_live(
    console: Console, api: KrixilApi, instruction: str, dir_: str, model: str
) -> None:
    """Submits one goal and renders its transcript live until it reaches a terminal status —
    the terminal equivalent of lib/api/agents.ts#pollAgentRun driving the web transcript, right
    down to Ctrl+C mapping to the same POST /agents/{id}/cancel the web's "esc to interrupt"
    button calls."""
    from krixil_cli.render import render_transcript  # local import avoids a cycle with main.py

    goal_text = build_goal(instruction, dir_)
    try:
        started = api.run_agent(goal_text, model)
    except ApiError as exc:
        console.print(f"[red]Couldn't start that run: {exc.detail}[/red]")
        return

    run = started
    start = time.monotonic()
    console.print()
    try:
        with Live(console=console, refresh_per_second=6, transient=False) as live:
            while True:
                try:
                    run = api.get_status(run.id)
                except ApiError as exc:
                    console.print(f"[red]Lost track of that run: {exc.detail}[/red]")
                    return
                live.update(
                    render_transcript(instruction, run.steps, run.status, time.monotonic() - start)
                )
                if run.status != "running":
                    break
                time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopping…[/dim]")
        try:
            api.cancel(run.id)
        except ApiError:
            pass
        # One more fetch so the transcript reflects the real final state (cancelled, or it
        # actually finished in the gap between the last poll and Ctrl+C) rather than freezing on
        # a stale "running" render.
        try:
            run = api.get_status(run.id)
            console.print(
                render_transcript(instruction, run.steps, run.status, time.monotonic() - start)
            )
        except ApiError:
            pass

    console.print()
    if run.error_message:
        console.print(f"[red]{run.error_message}[/red]")


def _model_choices(api: KrixilApi) -> list[ModelInfo]:
    try:
        return api.list_models()
    except ApiError:
        return []


def interactive_loop(console: Console, api: KrixilApi, host_root: str, initial_dir: str) -> None:
    model = "auto"
    dir_ = initial_dir
    console.print(
        f"[dim]Working in[/dim] [bold]{dir_}[/bold] [dim]under {host_root}. "
        "/model to switch models, /cwd to reset the folder, /exit to quit.[/dim]\n"
    )

    while True:
        try:
            instruction = Prompt.ask("[bold cyan]›[/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not instruction:
            continue

        if instruction in ("/exit", "/quit"):
            break
        if instruction == "/help":
            console.print(
                "[dim]/model  — switch model\n"
                "/cwd    — show/reset the folder this CLI operates in\n"
                "/exit   — quit[/dim]"
            )
            continue
        if instruction == "/cwd":
            console.print(f"[dim]Currently working in {dir_} under {host_root}.[/dim]")
            continue
        if instruction == "/model":
            models = _model_choices(api)
            if not models:
                console.print("[dim]Couldn't load the model list.[/dim]")
                continue
            for i, m in enumerate(models, 1):
                marker = "*" if m.id == model else " "
                console.print(
                    f"  {marker} {i}. [bold]{m.name}[/bold] [dim]({m.id})[/dim] — {m.description}"
                )
            choice = Prompt.ask("Pick a number", default="")
            if choice.isdigit() and 1 <= int(choice) <= len(models):
                model = models[int(choice) - 1].id
                console.print(f"[dim]Switched to {model}.[/dim]")
            continue

        run_goal_live(console, api, instruction, dir_, model)
