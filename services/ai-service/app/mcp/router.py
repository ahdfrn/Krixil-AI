import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.mcp.client import list_server_tools
from app.mcp.service import (
    create_mcp_server,
    delete_mcp_server,
    get_mcp_server_or_404,
    list_mcp_servers,
)
from app.schemas.mcp import MCPServerCreate, MCPServerOut, MCPToolOut
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _redact(server) -> MCPServerOut:
    # Real env *keys* are useful to see at a glance (e.g. confirming GITHUB_TOKEN is set at all);
    # real values are secrets (API tokens, etc.) that shouldn't come back over the API once set —
    # redacted here, the real values are still what's actually used to connect (app/mcp/client.py
    # reads them straight from the MCPServer row, not from this response).
    redacted_env = {k: "***" for k in server.env}
    return MCPServerOut(
        id=server.id,
        name=server.name,
        command=server.command,
        args=server.args,
        env=redacted_env,
        created_at=server.created_at,
    )


@router.post("/servers", response_model=MCPServerOut)
async def add_server(
    payload: MCPServerCreate,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> MCPServerOut:
    server = await create_mcp_server(
        session, tenant_ctx, payload.name, payload.command, payload.args, payload.env
    )
    await session.commit()
    return _redact(server)


@router.get("/servers", response_model=list[MCPServerOut])
async def list_servers(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[MCPServerOut]:
    servers = await list_mcp_servers(session, tenant_ctx)
    return [_redact(s) for s in servers]


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_server(
    server_id: uuid.UUID,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> None:
    await delete_mcp_server(session, tenant_ctx, server_id)
    await session.commit()


@router.get("/servers/{server_id}/tools", response_model=list[MCPToolOut])
async def get_server_tools(
    server_id: uuid.UUID,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[MCPToolOut]:
    """A real, live connection test — connects to the real configured server right now and
    returns whatever it actually advertises, surfacing a real, clear error if it can't."""
    server = await get_mcp_server_or_404(session, tenant_ctx, server_id)
    try:
        tools = await list_server_tools(server)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [
        MCPToolOut(name=t.name, description=t.description, input_schema=t.input_schema)
        for t in tools
    ]
