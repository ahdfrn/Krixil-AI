"""Real MCP (Model Context Protocol) client — PRD §10's MCP Hub. Uses the official `mcp` Python
SDK (not a hand-rolled JSON-RPC client) to speak the real protocol: connect, do the real
`initialize` handshake, then `tools/list`/`tools/call`. Three real transports: `stdio` (a real
local subprocess, e.g. `npx -y @modelcontextprotocol/server-filesystem <path>`), `sse`, and `http`
(streamable HTTP) — both remote transports reach a real MCP server over the network. A fresh
connection per call, not a persisted one — MCP servers are typically cheap to (re)connect and this
avoids managing long-lived subprocess/connection lifecycles across concurrent requests.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from app.core.config import get_settings
from app.models.mcp_server import MCPServer


class MCPToolSchema:
    def __init__(self, name: str, description: str | None, input_schema: dict):
        self.name = name
        self.description = description or ""
        self.input_schema = input_schema


def _stdio_params(server: MCPServer) -> StdioServerParameters:
    # `command` is only ever None for a non-stdio server — MCPServerCreate's validator guarantees
    # a stdio server always has one; this assert just narrows the type for mypy.
    assert server.command is not None
    return StdioServerParameters(
        command=server.command, args=list(server.args), env=server.env or None
    )


def _find_http_error(exc: BaseException) -> httpx.HTTPError | None:
    """The sse/streamable-http transports run their real connection inside an anyio TaskGroup, so
    a real connection failure (e.g. an unreachable host) surfaces as an `ExceptionGroup` wrapping
    the real `httpx.HTTPError`, not the error itself — unwrap it so the same clear ValueError path
    below fires regardless of how deep the SDK nested it."""
    if isinstance(exc, httpx.HTTPError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _find_http_error(sub)
            if found is not None:
                return found
    return None


@asynccontextmanager
async def _connect(server: MCPServer, timeout: float) -> AsyncIterator[tuple]:
    """The one real chokepoint that dispatches on `server.transport` — normalizes all three
    transports down to the same `(read, write)` 2-tuple `ClientSession` expects, so
    `list_server_tools`/`call_server_tool` below don't need to know which transport they're on."""
    if server.transport == "stdio":
        async with stdio_client(_stdio_params(server)) as (read, write):
            yield read, write
    elif server.transport == "sse":
        # `url` is only ever None for a stdio server — MCPServerCreate's validator guarantees a
        # remote server always has one; this assert just narrows the type for mypy.
        assert server.url is not None
        async with sse_client(
            server.url, headers=server.headers or None, timeout=timeout, sse_read_timeout=timeout
        ) as (read, write):
            yield read, write
    elif server.transport == "http":
        assert server.url is not None
        async with streamablehttp_client(
            server.url, headers=server.headers or None, timeout=timeout, sse_read_timeout=timeout
        ) as (read, write, _get_session_id):
            yield read, write
    else:  # pragma: no cover - MCPServerCreate's Literal makes this unreachable via the API
        raise ValueError(
            f"MCP server '{server.name}' has an unknown transport '{server.transport}'."
        )


async def list_server_tools(server: MCPServer) -> list[MCPToolSchema]:
    """A real connection, real handshake, real `tools/list` call — whatever the server actually
    advertises right now, not a cached or fabricated list."""
    timeout = get_settings().mcp_timeout_seconds
    try:

        async def _run() -> list[MCPToolSchema]:
            async with _connect(server, timeout) as (read, write):
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
    except httpx.HTTPError as exc:
        raise ValueError(
            f"Couldn't reach MCP server '{server.name}' (url: {server.url!r}): {exc}"
        ) from exc
    except ExceptionGroup as exc:
        http_error = _find_http_error(exc)
        if http_error is None:
            raise
        raise ValueError(
            f"Couldn't reach MCP server '{server.name}' (url: {server.url!r}): {http_error}"
        ) from exc


async def call_server_tool(server: MCPServer, tool_name: str, arguments: dict) -> dict:
    """A real connection, real `tools/call` — the actual real result an MCP tool call produces
    right now, good or bad. Text content blocks are joined into one real string; non-text content
    (images, etc.) is noted by type rather than silently dropped or fabricated as text."""
    timeout = get_settings().mcp_timeout_seconds
    try:

        async def _run() -> dict:
            async with _connect(server, timeout) as (read, write):
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
    except httpx.HTTPError as exc:
        raise ValueError(
            f"Couldn't reach MCP server '{server.name}' (url: {server.url!r}): {exc}"
        ) from exc
    except ExceptionGroup as exc:
        http_error = _find_http_error(exc)
        if http_error is None:
            raise
        raise ValueError(
            f"Couldn't reach MCP server '{server.name}' (url: {server.url!r}): {http_error}"
        ) from exc
