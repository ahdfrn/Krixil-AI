"""Real, unsandboxed access to a folder on this machine (services/host-runner), for tenants who
explicitly opted into "This Computer" mode on the Code page instead of the isolated
workspace_root sandbox (app/tools/code_tools.py). No tenant scoping here — host-runner has no
concept of tenants, only a single HOST_ROOT for the one real user of this deployment. See
docs/architecture/coding-agent.md ("Real host-folder access") for the full trade-off."""

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, Tool, register_tool
from app.tools.risk_rules import find_block_reason

_UNREACHABLE_MESSAGE = (
    "host-runner isn't reachable — is it running? See services/host-runner/README.md."
)


def _raise_for_status_with_detail(response: httpx.Response) -> None:
    """httpx's own HTTPStatusError.__str__ doesn't include the response body, so a host-runner
    rejection (e.g. a path-confinement error) would otherwise surface to the user as an opaque
    "400 Bad Request" instead of the real reason. Re-raised as ValueError, matching how
    app/tools/code_tools.py surfaces its own WorkspacePathError/FileNotFoundError — the generic
    handler in app/tools/service.py turns any exception's str() into the execution's
    error_message, so this is what the user (or an Agent reacting to a failed tool call) sees."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise ValueError(str(detail)) from exc


class HostListFilesInput(BaseModel):
    path: str = Field(default=".", max_length=1000)


async def _host_list_files_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: HostListFilesInput
) -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.host_runner_timeout_seconds) as client:
            response = await client.get(
                f"{settings.host_runner_url}/files", params={"path": params.path}
            )
    except httpx.ConnectError as exc:
        raise ValueError(_UNREACHABLE_MESSAGE) from exc
    _raise_for_status_with_detail(response)
    return {"entries": response.json()}


register_tool(
    Tool(
        name="host.list_files",
        description="List files and folders under HOST_ROOT on the real machine Krixil runs on "
        "— not the isolated sandbox workspace. Only available when the host-runner service is "
        "running.",
        input_model=HostListFilesInput,
        risk_level=RiskLevel.LOW,
        required_permission="host:read",
        handler=_host_list_files_handler,
    )
)


class HostReadFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


async def _host_read_file_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: HostReadFileInput
) -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.host_runner_timeout_seconds) as client:
            response = await client.get(
                f"{settings.host_runner_url}/files/content", params={"path": params.path}
            )
    except httpx.ConnectError as exc:
        raise ValueError(_UNREACHABLE_MESSAGE) from exc
    _raise_for_status_with_detail(response)
    return response.json()


register_tool(
    Tool(
        name="host.read_file",
        description="Read a file under HOST_ROOT on the real machine Krixil runs on — not the "
        "isolated sandbox workspace.",
        input_model=HostReadFileInput,
        risk_level=RiskLevel.LOW,
        required_permission="host:read",
        handler=_host_read_file_handler,
    )
)


class HostWriteFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=1_000_000)


async def _host_write_file_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: HostWriteFileInput
) -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.host_runner_timeout_seconds) as client:
            response = await client.post(
                f"{settings.host_runner_url}/files",
                json={"path": params.path, "content": params.content},
            )
    except httpx.ConnectError as exc:
        raise ValueError(_UNREACHABLE_MESSAGE) from exc
    _raise_for_status_with_detail(response)
    return {"path": params.path, "written": True}


register_tool(
    Tool(
        name="host.write_file",
        description="Create or overwrite a real file under HOST_ROOT on the machine Krixil runs "
        "on. No sandbox, no approval — this really changes a file on disk. Destructive if the "
        "file already exists. For changing part of an existing file, prefer host.edit_file — "
        "it's a precise, reviewable change instead of reproducing the whole file from memory.",
        input_model=HostWriteFileInput,
        # MEDIUM, not CRITICAL/approval-gated — matches the deliberate choice already made for
        # the sandboxed code.* tools (see app/tools/code_tools.py), extended here even though
        # this one has no sandbox left underneath it at all. An explicit, informed trade-off, not
        # an oversight — see docs/architecture/coding-agent.md.
        risk_level=RiskLevel.MEDIUM,
        required_permission="host:write",
        handler=_host_write_file_handler,
    )
)


class HostEditFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    old_string: str = Field(min_length=1, max_length=500_000)
    new_string: str = Field(max_length=500_000)


async def _host_edit_file_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: HostEditFileInput
) -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.host_runner_timeout_seconds) as client:
            read_response = await client.get(
                f"{settings.host_runner_url}/files/content", params={"path": params.path}
            )
    except httpx.ConnectError as exc:
        raise ValueError(_UNREACHABLE_MESSAGE) from exc
    _raise_for_status_with_detail(read_response)
    content = read_response.json()["content"]

    occurrences = content.count(params.old_string)
    if occurrences == 0:
        raise ValueError(
            f"old_string not found in '{params.path}' — read the file first and copy the exact "
            "text, including whitespace."
        )
    if occurrences > 1:
        raise ValueError(
            f"old_string appears {occurrences} times in '{params.path}' — include more "
            "surrounding context so it uniquely identifies one location."
        )

    new_content = content.replace(params.old_string, params.new_string, 1)
    try:
        async with httpx.AsyncClient(timeout=settings.host_runner_timeout_seconds) as client:
            write_response = await client.post(
                f"{settings.host_runner_url}/files",
                json={"path": params.path, "content": new_content},
            )
    except httpx.ConnectError as exc:
        raise ValueError(_UNREACHABLE_MESSAGE) from exc
    _raise_for_status_with_detail(write_response)
    return {"path": params.path, "edited": True}


register_tool(
    Tool(
        name="host.edit_file",
        description="Replace one exact, unique occurrence of old_string with new_string in a "
        "real file under HOST_ROOT — a precise, surgical change instead of rewriting the whole "
        "file (host.write_file). old_string must appear exactly once in the file (read it first "
        "to copy the exact text) or this fails with a clear error rather than guessing which "
        "occurrence you meant.",
        input_model=HostEditFileInput,
        # Same tier as host.write_file — a file mutation either way, see that tool's own comment.
        risk_level=RiskLevel.MEDIUM,
        required_permission="host:write",
        handler=_host_edit_file_handler,
    )
)


class HostSearchFilesInput(BaseModel):
    pattern: str = Field(min_length=1, max_length=500)
    path: str = Field(default=".", max_length=1000)


async def _host_search_files_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: HostSearchFilesInput
) -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.host_runner_timeout_seconds) as client:
            response = await client.get(
                f"{settings.host_runner_url}/search",
                params={"pattern": params.pattern, "path": params.path},
            )
    except httpx.ConnectError as exc:
        raise ValueError(_UNREACHABLE_MESSAGE) from exc
    _raise_for_status_with_detail(response)
    return {"results": response.json()}


register_tool(
    Tool(
        name="host.search_files",
        description="Search real files under HOST_ROOT for a regex pattern, recursively — real "
        "matches with path and line number, not a directory listing you'd have to read through "
        "yourself. Skips node_modules/.git/venv/binary files. Capped at 200 results.",
        input_model=HostSearchFilesInput,
        risk_level=RiskLevel.LOW,
        required_permission="host:read",
        handler=_host_search_files_handler,
    )
)


class HostRunCommandInput(BaseModel):
    directory: str = Field(default=".", max_length=1000)
    command: str = Field(min_length=1, max_length=4000)
    # Wide upper bound deliberately — see code_tools.py's CodeRunCommandInput.timeout_seconds for
    # why: the real ceiling is the min() clamp against settings.host_runner_timeout_seconds below,
    # not this field.
    timeout_seconds: int = Field(default=60, ge=1, le=600)


def _host_run_command_risk_classifier(params: HostRunCommandInput) -> str | None:
    return find_block_reason(params.command)


async def _host_run_command_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: HostRunCommandInput
) -> dict:
    settings = get_settings()
    timeout = min(params.timeout_seconds, settings.host_runner_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            response = await client.post(
                f"{settings.host_runner_url}/run",
                json={
                    "directory": params.directory,
                    "command": params.command,
                    "timeout_seconds": timeout,
                },
            )
    except httpx.ConnectError as exc:
        raise ValueError(_UNREACHABLE_MESSAGE) from exc
    _raise_for_status_with_detail(response)
    return response.json()


register_tool(
    Tool(
        name="host.run_command",
        description="Run a shell command for real on the machine Krixil runs on, under HOST_ROOT "
        "— no sandbox, no network restriction. Uses whatever is actually installed on this "
        "machine (the real Python, git, node, PATH). Returns stdout, stderr, exit code. "
        "HIGH risk — an agent run pauses and waits for a human to approve or reject the exact "
        "command before it executes (see app/tools/base.py's APPROVAL_REQUIRED_LEVELS and "
        "app/agents/runner.py).",
        input_model=HostRunCommandInput,
        # HIGH, unlike host.write_file's deliberate MEDIUM (see that tool's own comment) —
        # arbitrary shell execution is a strictly bigger blast radius than writing one file
        # (it can delete, network-call, or write anything write_file could and more), and it's
        # the PRD's own example of a HIGH-risk action (docs/architecture/kirxil-cli-prd.md §17).
        # This is what actually makes the Permission Engine real for the CLI/host path — before
        # this, nothing host.* ever reached RiskLevel.HIGH, so pending_approval never fired here.
        risk_level=RiskLevel.HIGH,
        required_permission="host:execute",
        handler=_host_run_command_handler,
        timeout_seconds=320.0,
        # A narrow, real BLOCK backstop on top of the HIGH-risk approval pause above — see
        # app/tools/risk_rules.py's docstring for exactly what this does and doesn't catch.
        risk_classifier=_host_run_command_risk_classifier,
    )
)


class HostDeleteFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


async def _host_delete_file_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: HostDeleteFileInput
) -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.host_runner_timeout_seconds) as client:
            response = await client.delete(
                f"{settings.host_runner_url}/files", params={"path": params.path}
            )
    except httpx.ConnectError as exc:
        raise ValueError(_UNREACHABLE_MESSAGE) from exc
    _raise_for_status_with_detail(response)
    return {"path": params.path, "deleted": True}


register_tool(
    Tool(
        name="host.delete_file",
        description="Permanently delete a real file under HOST_ROOT on the machine Krixil runs "
        "on. Cannot delete a directory. HIGH risk — an agent run pauses and waits for a human to "
        "approve or reject the exact path before it deletes anything (same mechanism as "
        "host.run_command). If the current directory is a git repo, `kirxil run`/the interactive "
        "REPL already checkpointed it before this run started (cli/src/checkpoint.ts) — "
        "`kirxil undo` can still get a deleted file back either way.",
        input_model=HostDeleteFileInput,
        # HIGH, not MEDIUM like write_file/edit_file — deletion is a strictly different kind of
        # destructive than overwriting or editing: a write/edit's previous content is still one
        # more write/edit away from being restored (the model can just put it back if asked), but
        # a deleted file is actually gone from this tool's own perspective — the only way back is
        # the checkpoint safety net, not this tool undoing itself. Matches host.run_command's
        # tier and reasoning: a bigger, less-reversible blast radius earns a human in the loop.
        risk_level=RiskLevel.HIGH,
        required_permission="host:write",
        handler=_host_delete_file_handler,
    )
)
