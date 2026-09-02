from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.client import call_server_tool, list_server_tools
from app.mcp.service import get_mcp_server_by_name_or_404, list_mcp_servers
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, Tool, register_tool


class MCPListServersInput(BaseModel):
    pass


async def _mcp_list_servers_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: MCPListServersInput
) -> dict:
    servers = await list_mcp_servers(session, tenant_ctx)
    return {"servers": [{"name": s.name, "command": s.command} for s in servers]}


register_tool(
    Tool(
        name="mcp.list_servers",
        description="List this tenant's configured real MCP servers (see `kirxil mcp add`) — "
        "just names/commands from the database, no live connection made.",
        input_model=MCPListServersInput,
        risk_level=RiskLevel.LOW,
        required_permission="host:read",
        handler=_mcp_list_servers_handler,
    )
)


class MCPListToolsInput(BaseModel):
    server_name: str = Field(min_length=1, max_length=100)


async def _mcp_list_tools_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: MCPListToolsInput
) -> dict:
    server = await get_mcp_server_by_name_or_404(session, tenant_ctx, params.server_name)
    tools = await list_server_tools(server)
    return {
        "tools": [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]
    }


register_tool(
    Tool(
        name="mcp.list_tools",
        description="Real, live connection to a configured MCP server (see mcp.list_servers) — "
        "returns whatever real tools it actually advertises right now, not a cached list.",
        input_model=MCPListToolsInput,
        risk_level=RiskLevel.LOW,
        required_permission="host:read",
        handler=_mcp_list_tools_handler,
        timeout_seconds=45.0,
    )
)


class MCPCallToolInput(BaseModel):
    server_name: str = Field(min_length=1, max_length=100)
    tool_name: str = Field(min_length=1, max_length=200)
    arguments: dict = Field(default_factory=dict)


async def _mcp_call_tool_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: MCPCallToolInput
) -> dict:
    server = await get_mcp_server_by_name_or_404(session, tenant_ctx, params.server_name)
    return await call_server_tool(server, params.tool_name, params.arguments)


register_tool(
    Tool(
        name="mcp.call_tool",
        description="Call a real tool on a configured MCP server — the real, unknown blast "
        "radius of a third-party MCP server's own tool (could read, write, or call out to "
        "anything that server itself can reach). HIGH risk — an agent run pauses and waits for "
        "a human to approve the exact server/tool/arguments before it runs, same as "
        "host.run_command.",
        input_model=MCPCallToolInput,
        risk_level=RiskLevel.HIGH,
        required_permission="host:execute",
        handler=_mcp_call_tool_handler,
        timeout_seconds=45.0,
    )
)
