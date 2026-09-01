"""Entry point — `krixil` (interactive), `krixil run "<goal>"` (one-shot), `krixil login`/`logout`.
See cli/README.md for setup. Talks to the same services/ai-service backend the web app does —
nothing here is a separate implementation of the agent loop, just another client of it."""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.prompt import Prompt

from krixil_cli.api import ApiError, KrixilApi
from krixil_cli.config import Session, clear_session, env_login, load_session, save_session
from krixil_cli.goal import dir_from_cwd
from krixil_cli.repl import interactive_loop, run_goal_live

app = typer.Typer(
    name="krixil",
    help="A terminal coding agent for your own Krixil AI backend — real, unsandboxed access to "
    "whatever folder you launch it from, same tools and live transcript the web app's Code page "
    "uses, driven from the command line.",
    add_completion=False,
)
console = Console()
DEFAULT_BASE_URL = "http://localhost:8000/api/v1"


@app.command()
def login(
    base_url: str = typer.Option(DEFAULT_BASE_URL, help="Krixil api service base URL."),
    host_root: str = typer.Option(
        ...,
        prompt=True,
        help="The real folder host.* tools operate under on this machine "
        "(see services/host-runner/.env's HOST_ROOT).",
    ),
) -> None:
    """Log in once and remember the session in ~/.krixil/credentials.json."""
    tenant_slug = Prompt.ask("Workspace slug")
    email = Prompt.ask("Email")
    password = Prompt.ask("Password", password=True)

    api = KrixilApi(base_url)
    try:
        result = api.login(tenant_slug, email, password)
    except ApiError as exc:
        console.print(f"[red]Login failed: {exc.detail}[/red]")
        raise typer.Exit(1) from None
    finally:
        api.close()

    save_session(
        Session(
            base_url=base_url,
            tenant_slug=result.tenant_slug,
            access_token=result.access_token,
            host_root=host_root,
        )
    )
    console.print(
        f"[green]Logged in as {tenant_slug}.[/green] Session saved to ~/.krixil/credentials.json."
    )


@app.command()
def logout() -> None:
    """Forget the saved session."""
    clear_session()
    console.print("Logged out.")


def _resolve_client() -> tuple[KrixilApi, str]:
    """Stored session (from `krixil login`) takes priority; falls back to
    KRIXIL_TENANT_SLUG/KRIXIL_EMAIL/KRIXIL_PASSWORD env vars (same three training/client.py
    reads) for scripted use with no interactive login step. Exits with a clear message rather
    than crashing on a None token if neither is available."""
    session = load_session()
    if session is not None:
        return KrixilApi(session.base_url, session.access_token), session.host_root

    env = env_login()
    if env is not None:
        slug, email, password = env
        api = KrixilApi(DEFAULT_BASE_URL)
        try:
            api.login(slug, email, password)
        except ApiError as exc:
            console.print(f"[red]Login failed: {exc.detail}[/red]")
            raise typer.Exit(1) from None
        host_root = "D:\\"  # No interactive login happened to ask for one; a reasonable guess,
        # overridable by running `krixil login` once instead for the real value.
        return api, host_root

    console.print(
        "[red]Not logged in.[/red] Run [bold]krixil login[/bold] first, or set "
        "KRIXIL_TENANT_SLUG/KRIXIL_EMAIL/KRIXIL_PASSWORD."
    )
    raise typer.Exit(1)


@app.command()
def run(
    goal: str = typer.Argument(..., help="The goal to run, once, non-interactively."),
    model: str = typer.Option("auto", help='Model id from `krixil models`, or "auto".'),
    dir_: str = typer.Option(
        None,
        "--dir",
        help="Folder to work in, relative to HOST_ROOT "
        "(defaults to wherever this is launched from).",
    ),
) -> None:
    """Run one goal and exit — for scripting, not the interactive feel of plain `krixil`."""
    api, host_root = _resolve_client()
    try:
        run_goal_live(
            console, api, goal, dir_ if dir_ is not None else dir_from_cwd(host_root), model
        )
    finally:
        api.close()


@app.command(name="models")
def list_models_cmd() -> None:
    """List the models this backend currently offers."""
    api, _ = _resolve_client()
    try:
        for m in api.list_models():
            console.print(f"[bold]{m.name}[/bold] [dim]({m.id})[/dim] — {m.description}")
    except ApiError as exc:
        console.print(f"[red]{exc.detail}[/red]")
    finally:
        api.close()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    api, host_root = _resolve_client()
    try:
        interactive_loop(console, api, host_root, dir_from_cwd(host_root))
    finally:
        api.close()


def entrypoint() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    entrypoint()
