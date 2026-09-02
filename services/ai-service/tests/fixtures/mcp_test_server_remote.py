"""A real, minimal MCP server exposed over a remote transport (sse or streamable-http) — used
only by test_mcp_client_remote.py. Same add/fail tools as mcp_test_server.py (the stdio fixture),
just reachable over real HTTP instead of a subprocess's stdin/stdout, to prove the sse_client/
streamablehttp_client code paths in app/mcp/client.py against a genuine server, not a mock.

Run directly: `python tests/fixtures/mcp_test_server_remote.py <transport> <port>`
  transport: "sse" or "streamable-http"
  port: a real, already-bound port (the caller picks one free to avoid CI collisions)
"""

import sys

from mcp.server.fastmcp import FastMCP


def build_server(port: int) -> FastMCP:
    server = FastMCP("kirxil-test-server-remote", host="127.0.0.1", port=port)

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two real numbers."""
        return a + b

    @server.tool()
    def fail() -> str:
        """Always raises, to exercise the real error path."""
        raise ValueError("this tool always fails, on purpose")

    return server


if __name__ == "__main__":
    transport, port = sys.argv[1], int(sys.argv[2])
    build_server(port).run(transport=transport)
