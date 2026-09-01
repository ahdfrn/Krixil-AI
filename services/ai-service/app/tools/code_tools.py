import httpx
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, Tool, register_tool
from app.workspace.fs import (
    WorkspacePathError,
    delete_file,
    list_files,
    read_file,
    search_files,
    write_file,
)


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
        "the file already exists — the previous content is not recoverable. For changing part of "
        "an existing file, prefer code.edit_file — a precise, reviewable change instead of "
        "reproducing the whole file from memory.",
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


class CodeEditFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    old_string: str = Field(min_length=1, max_length=500_000)
    new_string: str = Field(max_length=500_000)


async def _code_edit_file_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: CodeEditFileInput
) -> dict:
    try:
        content = read_file(tenant_ctx.tenant_id, params.path)
    except WorkspacePathError as exc:
        raise ValueError(str(exc)) from exc
    except FileNotFoundError as exc:
        raise ValueError(f"'{params.path}' does not exist") from exc

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
        write_file(tenant_ctx.tenant_id, params.path, new_content)
    except WorkspacePathError as exc:
        raise ValueError(str(exc)) from exc
    return {"path": params.path, "edited": True}


register_tool(
    Tool(
        name="code.edit_file",
        description="Replace one exact, unique occurrence of old_string with new_string in a "
        "file in the tenant's coding workspace — a precise, surgical change instead of rewriting "
        "the whole file (code.write_file). old_string must appear exactly once in the file (read "
        "it first to copy the exact text) or this fails with a clear error rather than guessing "
        "which occurrence you meant.",
        input_model=CodeEditFileInput,
        risk_level=RiskLevel.MEDIUM,
        required_permission="code:write",
        handler=_code_edit_file_handler,
    )
)


class CodeSearchFilesInput(BaseModel):
    pattern: str = Field(min_length=1, max_length=500)
    path: str = Field(default=".", max_length=500)


async def _code_search_files_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: CodeSearchFilesInput
) -> dict:
    try:
        return {"results": search_files(tenant_ctx.tenant_id, params.pattern, params.path)}
    except WorkspacePathError as exc:
        raise ValueError(str(exc)) from exc


register_tool(
    Tool(
        name="code.search_files",
        description="Search files in the tenant's coding workspace for a regex pattern, "
        "recursively — real matches with path and line number, not a directory listing you'd "
        "have to read through yourself. Skips node_modules/.git/venv/binary files. Capped at "
        "200 results.",
        input_model=CodeSearchFilesInput,
        risk_level=RiskLevel.LOW,
        required_permission="code:read",
        handler=_code_search_files_handler,
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


class CodeDeleteFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=500)


async def _code_delete_file_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: CodeDeleteFileInput
) -> dict:
    try:
        delete_file(tenant_ctx.tenant_id, params.path)
    except WorkspacePathError as exc:
        raise ValueError(str(exc)) from exc
    except IsADirectoryError as exc:
        raise ValueError(f"'{params.path}' is a directory") from exc
    return {"path": params.path, "deleted": True}


register_tool(
    Tool(
        name="code.delete_file",
        description="Permanently delete a file in the tenant's coding workspace. Cannot delete a "
        "directory. HIGH risk — an agent run pauses and waits for a human to approve or reject "
        "the exact path before it deletes anything.",
        input_model=CodeDeleteFileInput,
        # HIGH, not MEDIUM like write_file/edit_file — see host.delete_file's own comment
        # (app/tools/host_tools.py) for the same reasoning: deletion isn't one more write away
        # from being undone the way an overwrite or edit is.
        risk_level=RiskLevel.HIGH,
        required_permission="code:write",
        handler=_code_delete_file_handler,
    )
)
