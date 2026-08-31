import httpx
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, Tool, register_tool
from app.workspace.fs import WorkspacePathError, list_files, read_file, write_file


class CodeListFilesInput(BaseModel):
    path: str = Field(default=".", max_length=500)


async def _code_list_files_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: CodeListFilesInput
) -> dict:
    try:
        return {"entries": list_files(tenant_ctx.tenant_id, params.path)}
    except WorkspacePathError as exc:
        raise ValueError(str(exc)) from exc


register_tool(
    Tool(
        name="code.list_files",
        description="List files and folders in the tenant's coding workspace.",
        input_model=CodeListFilesInput,
        risk_level=RiskLevel.LOW,
        required_permission="code:read",
        handler=_code_list_files_handler,
    )
)


class CodeReadFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=500)


async def _code_read_file_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: CodeReadFileInput
) -> dict:
    try:
        content = read_file(tenant_ctx.tenant_id, params.path)
    except WorkspacePathError as exc:
        raise ValueError(str(exc)) from exc
    except FileNotFoundError as exc:
        raise ValueError(f"'{params.path}' does not exist") from exc
    return {"path": params.path, "content": content}


register_tool(
    Tool(
        name="code.read_file",
        description="Read the contents of a file in the tenant's coding workspace.",
        input_model=CodeReadFileInput,
        risk_level=RiskLevel.LOW,
        required_permission="code:read",
        handler=_code_read_file_handler,
    )
)


class CodeWriteFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=1_000_000)


async def _code_write_file_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: CodeWriteFileInput
) -> dict:
    try:
        write_file(tenant_ctx.tenant_id, params.path, params.content)
    except WorkspacePathError as exc:
        raise ValueError(str(exc)) from exc
    return {"path": params.path, "written": True}


register_tool(
    Tool(
        name="code.write_file",
        description="Create or overwrite a file in the tenant's coding workspace. Destructive if "
        "the file already exists — the previous content is not recoverable.",
        input_model=CodeWriteFileInput,
        # MEDIUM, not CRITICAL — runs immediately, no human-approval pause. Explicit tradeoff the
        # user asked for after being told what it means (full, uninterrupted read/write/run
        # access, like a real coding agent, rather than pausing on every step). Still confined to
        # the tenant's own workspace directory (WorkspacePathError) and still LOW/MEDIUM-only, so
        # it's still never offered to plain Chat (app/chat/tool_use.py only offers LOW-risk
        # tools) — only reachable via the Agents loop.
        risk_level=RiskLevel.MEDIUM,
        required_permission="code:write",
        handler=_code_write_file_handler,
    )
)


class CodeRunCommandInput(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    # Wide upper bound deliberately — the real ceiling is the min() clamp against
    # settings.code_execution_timeout_seconds in the handler below, not this field. A tight le=120
    # here used to hard-reject the request outright whenever the model asked for more (caught
    # live, repeatedly: it kept requesting 300s), instead of letting the existing clamp bring an
    # over-ask back down to something safe. Better to accept and clamp than reject and confuse it.
    timeout_seconds: int = Field(default=30, ge=1, le=600)


async def _code_run_command_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: CodeRunCommandInput
) -> dict:
    settings = get_settings()
    timeout = min(params.timeout_seconds, settings.code_execution_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        response = await client.post(
            f"{settings.sandbox_runner_url}/run",
            json={
                "tenant_id": str(tenant_ctx.tenant_id),
                "command": params.command,
                "timeout_seconds": timeout,
            },
        )
        response.raise_for_status()
        return response.json()


register_tool(
    Tool(
        name="code.run_command",
        description="Run a shell command in an isolated, network-disabled sandbox container with "
        "the tenant's coding workspace mounted. Returns stdout, stderr, and exit code.",
        input_model=CodeRunCommandInput,
        # MEDIUM, not CRITICAL — see code.write_file's comment above for why. The sandbox itself
        # (network-disabled, resource-limited, workspace-confined — services/sandbox-runner) is
        # what still bounds the blast radius now that a human isn't approving each call.
        risk_level=RiskLevel.MEDIUM,
        required_permission="code:execute",
        handler=_code_run_command_handler,
        # Must exceed sandbox_runner_url's own request timeout above (up to
        # code_execution_timeout_seconds + 10s) plus container-startup overhead, or this tool's
        # own asyncio.wait_for (app/tools/service.py) would cancel the call before the sandbox
        # ever gets to return its result.
        timeout_seconds=180.0,
    )
)
