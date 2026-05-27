import asyncio
from types import SimpleNamespace

import pytest

from harness.mcp.client import MCPClient
from harness.mcp.types import MCPServerConfig


class FakeTransport:
    def __init__(self):
        self.enter_task = None
        self.exit_task = None

    async def __aenter__(self):
        self.enter_task = asyncio.current_task()
        return object(), object()

    async def __aexit__(self, exc_type, exc, tb):
        self.exit_task = asyncio.current_task()
        if self.exit_task is not self.enter_task:
            raise RuntimeError("transport exited in a different task")
        return None


class FakeSession:
    def __init__(self, read, write):
        self.read = read
        self.write = write
        self.enter_task = None
        self.exit_task = None

    async def __aenter__(self):
        self.enter_task = asyncio.current_task()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exit_task = asyncio.current_task()
        if self.exit_task is not self.enter_task:
            raise RuntimeError("session exited in a different task")
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
        transport = FakeTransport()
        seen["command"] = server.command
        seen["args"] = server.args
        seen["env"] = server.env
        seen["transport"] = transport
        return transport

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
    await client.disconnect()


@pytest.mark.asyncio
async def test_disconnect_exits_mcp_contexts_in_owner_task(monkeypatch):
    import mcp
    import mcp.client.stdio as stdio_module

    seen = {}

    def fake_stdio_client(server):
        transport = FakeTransport()
        seen["transport"] = transport
        return transport

    class CapturingSession(FakeSession):
        def __init__(self, read, write):
            super().__init__(read, write)
            seen["session"] = self

    monkeypatch.setattr(stdio_module, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(mcp, "ClientSession", CapturingSession)

    client = MCPClient(MCPServerConfig(
        name="sequential_thinking",
        transport="stdio",
        command="cmd",
        args=["/c", "npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
    ))

    await client.connect()
    await asyncio.create_task(client.disconnect())

    assert seen["transport"].exit_task is seen["transport"].enter_task
    assert seen["session"].exit_task is seen["session"].enter_task
    assert not client.is_connected()
