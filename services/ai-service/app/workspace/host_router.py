"""Human-driven browsing of a real folder on this machine, via host-runner — same shape as
app/workspace/router.py's tenant-isolated equivalent, but proxied over HTTP since host-runner is
a separate native-Windows process, not something this container can touch directly. Bypasses the
Tool System entirely, same as /workspace/files already does for a human using the Code page
directly (as opposed to an Agent's tool call)."""

from collections.abc import Awaitable, Callable

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context
from app.workspace.scope import host_headers

router = APIRouter(prefix="/host", tags=["workspace"])

_UNREACHABLE_DETAIL = (
    "host-runner isn't reachable — is it running? See services/host-runner/README.md."
)


class HostEntryOut(BaseModel):
    name: str
    path: str
    is_dir: bool
    size_bytes: int | None


class HostFileOut(BaseModel):
    path: str
    content: str


async def _proxy(
    call: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]], tenant_ctx: TenantContext
) -> httpx.Response:
    """Runs one request against host-runner, translating its failure modes into the same
    HTTPException shapes every other router in this app already raises — the client-side code
    only ever needs to handle ApiError, not know host-runner is a separate process."""
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.host_runner_url,
        timeout=settings.host_runner_timeout_seconds,
        headers=host_headers(tenant_ctx),
    ) as client:
        try:
            response = await call(client)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            try:
                detail = exc.response.json().get("detail", detail)
            except ValueError:
                pass
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_UNREACHABLE_DETAIL
            ) from exc


@router.get("/files", response_model=list[HostEntryOut])
async def get_files(
    path: str = ".", tenant_ctx: TenantContext = Depends(get_tenant_context)
) -> list[HostEntryOut]:
    _permission(tenant_ctx, "host:read")
    response = await _proxy(lambda client: client.get("/files", params={"path": path}), tenant_ctx)
    return [HostEntryOut(**e) for e in response.json()]


@router.get("/files/content", response_model=HostFileOut)
async def get_file_content(
    path: str, tenant_ctx: TenantContext = Depends(get_tenant_context)
) -> HostFileOut:
    _permission(tenant_ctx, "host:read")
    response = await _proxy(
        lambda client: client.get("/files/content", params={"path": path}), tenant_ctx
    )
    return HostFileOut(**response.json())


@router.post("/files", response_model=HostFileOut, status_code=status.HTTP_201_CREATED)
async def write_file(
    path: str, file: UploadFile = File(...), tenant_ctx: TenantContext = Depends(get_tenant_context)
) -> HostFileOut:
    _permission(tenant_ctx, "host:write")
    content = (await file.read()).decode("utf-8", errors="replace")
    response = await _proxy(
        lambda client: client.post("/files", json={"path": path, "content": content}), tenant_ctx
    )
    return HostFileOut(**response.json())


@router.delete("/files", status_code=status.HTTP_204_NO_CONTENT)
async def remove_file(path: str, tenant_ctx: TenantContext = Depends(get_tenant_context)) -> None:
    _permission(tenant_ctx, "host:write")
    await _proxy(lambda client: client.delete("/files", params={"path": path}), tenant_ctx)


def _permission(ctx: TenantContext, permission: str) -> None:
    if not ctx.has_permission(permission):
        raise HTTPException(status_code=403, detail="Missing host permission")


@router.get("/workspace")
async def workspace(tenant_ctx: TenantContext = Depends(get_tenant_context)) -> dict:
    if not tenant_ctx.workspace_root:
        raise HTTPException(status_code=400, detail="Workspace header required")
    response = await _proxy(lambda client: client.get("/workspace"), tenant_ctx)
    return response.json()
