"""A real, minimal MCP server (stdio transport) used only by test_mcp_client.py — spawned as a
real subprocess, speaking the real protocol, but built from the same `mcp` package already a
real dependency rather than needing network access to `npx` a third-party server (which the
filesystem-server smoke test during development used, but a test suite shouldn't depend on
network/npm availability). Run directly: `python tests/fixtures/mcp_test_server.py`.
"""

from mcp.server.fastmcp import FastMCP

server = FastMCP("kirxil-test-server")


@server.tool()
def add(a: int, b: int) -> int:
    """Add two real numbers."""
    return a + b


@server.tool()
def fail() -> str:
    """Always raises, to exercise the real error path."""
    raise ValueError("this tool always fails, on purpose")


if __name__ == "__main__":
    server.run(transport="stdio")
