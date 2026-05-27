from types import SimpleNamespace

import pytest

from harness.mcp.client import MCPClient
from harness.mcp.types import MCPServerConfig


class FakeTransport:
    async def __aenter__(self):
        return object(), object()

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakeSession:
    def __init__(self, read, write):
        self.read = read
        self.write = write

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def initialize(self):
        return None

    async def list_tools(self):
        tool = SimpleNamespace(
            name="sequential_thinking",
            description="Think step by step",
            inputSchema={"type": "object"},
            model_dump=lambda: {"name": "sequential_thinking"},
        )
        return SimpleNamespace(tools=[tool])


@pytest.mark.asyncio
async def test_stdio_client_uses_current_mcp_server_parameters(monkeypatch):
    from mcp.client.stdio import StdioServerParameters
    import mcp
    import mcp.client.stdio as stdio_module

    seen = {}

    def fake_stdio_client(server):
        assert isinstance(server, StdioServerParameters)
        seen["command"] = server.command
        seen["args"] = server.args
        seen["env"] = server.env
        return FakeTransport()

    monkeypatch.setattr(stdio_module, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(mcp, "ClientSession", FakeSession)

    client = MCPClient(MCPServerConfig(
        name="sequential_thinking",
        transport="stdio",
        command="cmd",
        args=["/c", "npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
        env={"MCP_TEST_ENV": "yes"},
    ))

    tools = await client.connect()

    assert seen["command"] == "cmd"
    assert seen["args"] == ["/c", "npx", "-y", "@modelcontextprotocol/server-sequential-thinking"]
    assert seen["env"]["MCP_TEST_ENV"] == "yes"
    assert tools[0].full_name == "sequential_thinking:sequential_thinking"
