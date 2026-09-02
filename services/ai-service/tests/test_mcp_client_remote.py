"""Real subprocess, real MCP protocol, over real HTTP — same discipline as test_mcp_client.py
(zero mocking of the MCP SDK): tests/fixtures/mcp_test_server_remote.py is a genuine MCP server
reachable over sse/streamable-http, not a stand-in for one."""

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.mcp.client import call_server_tool, list_server_tools
from app.models.mcp_server import MCPServer

_TEST_SERVER_SCRIPT = str(Path(__file__).parent / "fixtures" / "mcp_test_server_remote.py")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(port: int, timeout: float = 10.0) -> None:
    # A plain TCP connect check, not an HTTP request to the real /sse endpoint — that endpoint is
    # a long-lived event stream by design, so a full GET never "completes" the way a readiness
    # probe needs; a raw socket connect is enough to know uvicorn is actually accepting requests.
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError as exc:
            last_exc = exc
            time.sleep(0.1)
    raise RuntimeError(f"test MCP server never came up on port {port}") from last_exc


@pytest.fixture
def sse_server():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, _TEST_SERVER_SCRIPT, "sse", str(port)])
    try:
        _wait_until_up(port)
        yield MCPServer(
            name="test-sse", transport="sse", url=f"http://127.0.0.1:{port}/sse", headers={}
        )
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture
def http_server():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, _TEST_SERVER_SCRIPT, "streamable-http", str(port)])
    try:
        _wait_until_up(port)
        yield MCPServer(
            name="test-http", transport="http", url=f"http://127.0.0.1:{port}/mcp", headers={}
        )
    finally:
        proc.terminate()
        proc.wait(timeout=5)


async def test_list_server_tools_returns_the_real_advertised_tools_over_sse(sse_server):
    tools = await list_server_tools(sse_server)
    by_name = {t.name: t for t in tools}
    assert set(by_name) == {"add", "fail"}
    assert "Add two real numbers" in by_name["add"].description


async def test_call_server_tool_returns_a_real_result_over_sse(sse_server):
    result = await call_server_tool(sse_server, "add", {"a": 3, "b": 4})
    assert result == {"content": "7", "is_error": False}


async def test_call_server_tool_surfaces_a_real_tool_error_over_sse(sse_server):
    result = await call_server_tool(sse_server, "fail", {})
    assert result["is_error"] is True
    assert "this tool always fails, on purpose" in result["content"]


async def test_list_server_tools_returns_the_real_advertised_tools_over_http(http_server):
    tools = await list_server_tools(http_server)
    assert {t.name for t in tools} == {"add", "fail"}


async def test_call_server_tool_returns_a_real_result_over_http(http_server):
    result = await call_server_tool(http_server, "add", {"a": 10, "b": 32})
    assert result == {"content": "42", "is_error": False}


async def test_list_server_tools_raises_a_clear_error_for_an_unreachable_url():
    server = MCPServer(
        name="unreachable", transport="sse", url="http://127.0.0.1:1/sse", headers={}
    )
    with pytest.raises(ValueError, match="Couldn't reach MCP server"):
        await list_server_tools(server)
