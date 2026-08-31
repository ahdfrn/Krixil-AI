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
        "file already exists.",
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


class HostRunCommandInput(BaseModel):
    directory: str = Field(default=".", max_length=1000)
    command: str = Field(min_length=1, max_length=4000)
    # Wide upper bound deliberately — see code_tools.py's CodeRunCommandInput.timeout_seconds for
    # why: the real ceiling is the min() clamp against settings.host_runner_timeout_seconds below,
    # not this field.
    timeout_seconds: int = Field(default=60, ge=1, le=600)


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
        "— no sandbox, no network restriction, no approval. Uses whatever is actually installed "
        "on this machine (the real Python, git, node, PATH). Returns stdout, stderr, exit code.",
        input_model=HostRunCommandInput,
        risk_level=RiskLevel.MEDIUM,
        required_permission="host:execute",
        handler=_host_run_command_handler,
        timeout_seconds=320.0,
    )
)
