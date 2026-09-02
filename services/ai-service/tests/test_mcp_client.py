"""Real subprocess, real MCP protocol — tests/fixtures/mcp_test_server.py is a genuine MCP server
(built on the same `mcp` package this client uses), not a mock. Same reasoning as
checkpoint.test.ts's real git or host-runner's real filesystem tests: the thing worth testing is
that the real protocol round-trip actually works, not a stand-in for it."""

import sys
from pathlib import Path

import pytest

from app.mcp.client import call_server_tool, list_server_tools
from app.models.mcp_server import MCPServer

_TEST_SERVER_SCRIPT = str(Path(__file__).parent / "fixtures" / "mcp_test_server.py")


def _real_test_server(**overrides) -> MCPServer:
    defaults = {
        "name": "test",
        "command": sys.executable,
        "args": [_TEST_SERVER_SCRIPT],
        "env": {},
    }
    return MCPServer(**{**defaults, **overrides})


async def test_list_server_tools_returns_the_real_advertised_tools():
    tools = await list_server_tools(_real_test_server())
    by_name = {t.name: t for t in tools}
    assert set(by_name) == {"add", "fail"}
    assert "Add two real numbers" in by_name["add"].description


async def test_call_server_tool_returns_a_real_result():
    result = await call_server_tool(_real_test_server(), "add", {"a": 3, "b": 4})
    assert result == {"content": "7", "is_error": False}


async def test_call_server_tool_surfaces_a_real_tool_error_not_a_crash():
    result = await call_server_tool(_real_test_server(), "fail", {})
    assert result["is_error"] is True
    assert "this tool always fails, on purpose" in result["content"]


async def test_list_server_tools_raises_a_clear_error_for_an_unrunnable_command():
    server = _real_test_server(command="this-command-does-not-exist-anywhere")
    with pytest.raises(ValueError, match="Couldn't start MCP server"):
        await list_server_tools(server)
