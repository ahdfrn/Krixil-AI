"""Real MCP (Model Context Protocol) client — PRD §10's MCP Hub. Uses the official `mcp` Python
SDK (not a hand-rolled JSON-RPC client) to speak the real protocol: connect over stdio to a real
subprocess, do the real `initialize` handshake, then `tools/list`/`tools/call`. Stdio transport
only in this pass — a real, tenant-configured local subprocess (e.g. `npx -y
@modelcontextprotocol/server-filesystem <path>`), not a remote HTTP/SSE MCP server; that's a real,
separate transport this pass doesn't add. A fresh connection per call, not a persisted one — MCP
servers are typically cheap to (re)start and this avoids managing long-lived subprocess lifecycles
across concurrent requests.
"""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.config import get_settings
from app.models.mcp_server import MCPServer


class MCPToolSchema:
    def __init__(self, name: str, description: str | None, input_schema: dict):
        self.name = name
        self.description = description or ""
        self.input_schema = input_schema


def _server_params(server: MCPServer) -> StdioServerParameters:
    return StdioServerParameters(
        command=server.command, args=list(server.args), env=server.env or None
    )


async def list_server_tools(server: MCPServer) -> list[MCPToolSchema]:
    """A real connection, real handshake, real `tools/list` call — whatever the server actually
    advertises right now, not a cached or fabricated list."""
    timeout = get_settings().mcp_timeout_seconds
    try:

        async def _run() -> list[MCPToolSchema]:
            async with stdio_client(_server_params(server)) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [
                        MCPToolSchema(t.name, t.description, t.inputSchema) for t in result.tools
                    ]

        return await asyncio.wait_for(_run(), timeout=timeout)
    except TimeoutError as exc:
        raise ValueError(
            f"MCP server '{server.name}' didn't respond within {timeout}s."
        ) from exc
    except OSError as exc:
        raise ValueError(
            f"Couldn't start MCP server '{server.name}' (command: {server.command!r}): {exc}"
        ) from exc


async def call_server_tool(server: MCPServer, tool_name: str, arguments: dict) -> dict:
    """A real connection, real `tools/call` — the actual real result an MCP tool call produces
    right now, good or bad. Text content blocks are joined into one real string; non-text content
    (images, etc.) is noted by type rather than silently dropped or fabricated as text."""
    timeout = get_settings().mcp_timeout_seconds
    try:

        async def _run() -> dict:
            async with stdio_client(_server_params(server)) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    parts = []
                    for block in result.content:
                        text = getattr(block, "text", None)
                        parts.append(text if text is not None else f"[{block.type} content]")
                    return {"content": "\n".join(parts), "is_error": bool(result.isError)}

        return await asyncio.wait_for(_run(), timeout=timeout)
    except TimeoutError as exc:
        raise ValueError(
            f"MCP server '{server.name}' didn't respond within {timeout}s."
        ) from exc
    except OSError as exc:
        raise ValueError(
            f"Couldn't start MCP server '{server.name}' (command: {server.command!r}): {exc}"
        ) from exc
