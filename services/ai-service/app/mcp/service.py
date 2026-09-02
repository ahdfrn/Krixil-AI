import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_server import MCPServer
from app.tenancy.context import TenantContext


async def create_mcp_server(
    session: AsyncSession,
    tenant_ctx: TenantContext,
    name: str,
    command: str,
    args: list[str],
    env: dict[str, str],
) -> MCPServer:
    server = MCPServer(
        tenant_id=tenant_ctx.tenant_id, name=name, command=command, args=args, env=env
    )
    session.add(server)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An MCP server named '{name}' already exists.",
        ) from exc
    return server


async def list_mcp_servers(session: AsyncSession, tenant_ctx: TenantContext) -> list[MCPServer]:
    result = await session.execute(
        select(MCPServer)
        .where(MCPServer.tenant_id == tenant_ctx.tenant_id)
        .order_by(MCPServer.name.asc())
    )
    return list(result.scalars().all())


async def get_mcp_server_by_name_or_404(
    session: AsyncSession, tenant_ctx: TenantContext, name: str
) -> MCPServer:
    server = (
        await session.execute(
            select(MCPServer).where(
                MCPServer.tenant_id == tenant_ctx.tenant_id, MCPServer.name == name
            )
        )
    ).scalar_one_or_none()
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No MCP server named '{name}'."
        )
    return server


async def get_mcp_server_or_404(
    session: AsyncSession, tenant_ctx: TenantContext, server_id: uuid.UUID
) -> MCPServer:
    server = (
        await session.execute(
            select(MCPServer).where(
                MCPServer.id == server_id, MCPServer.tenant_id == tenant_ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    return server


async def delete_mcp_server(
    session: AsyncSession, tenant_ctx: TenantContext, server_id: uuid.UUID
) -> None:
    server = await get_mcp_server_or_404(session, tenant_ctx, server_id)
    await session.delete(server)
    await session.flush()
