"""MCPClient — manages a single MCP server connection and tool discovery."""

import asyncio
import os
import structlog
from contextlib import suppress
from typing import Any

from harness.mcp.types import MCPServerConfig, MCPToolInfo

logger = structlog.get_logger()


class MCPClient:
    """Manages a single MCP server connection (stdio or SSE), tool discovery, and invocation."""

    def __init__(self, server_config: MCPServerConfig):
        self.config = server_config
        self._session = None
        self._tools: list[dict] = []
        self._tools_info: list[MCPToolInfo] = []
        self._connected = False
        self._transport = None
        self._command_queue: asyncio.Queue | None = None
        self._owner_task: asyncio.Task | None = None
        self._ready_future: asyncio.Future | None = None
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> list[MCPToolInfo]:
        """Connect to the MCP server and discover its tools."""
        async with self._connect_lock:
            if self._connected:
                return self._tools_info

            if self._ready_future:
                return await self._ready_future

            loop = asyncio.get_running_loop()
            ready: asyncio.Future = loop.create_future()
            self._ready_future = ready
            self._command_queue = asyncio.Queue()
            self._owner_task = asyncio.create_task(
                self._run_connection(ready),
                name=f"mcp-client:{self.config.name}",
            )

            try:
                return await ready
            except Exception:
                if self._owner_task:
                    with suppress(Exception):
                        await self._owner_task
                raise
            finally:
                if self._ready_future is ready:
                    self._ready_future = None

    async def _run_connection(self, ready: asyncio.Future) -> None:
        """Own the MCP session lifecycle in one task.

        MCP's anyio cancel scope must be exited by the same task that entered it.
        FastAPI requests run in different tasks, so public methods proxy work to
        this owner task instead of directly entering/exiting the SDK contexts.
        """

        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.sse import sse_client

        disconnect_future: asyncio.Future | None = None
        try:
            env = os.environ.copy()
            for k, v in self.config.env.items():
                resolved = os.path.expandvars(v) if "$" in v else v
                env[k] = resolved

            if self.config.transport == "stdio":
                server_params = StdioServerParameters(
                    command=self.config.command,
                    args=self.config.args,
                    env=env,
                )
                self._transport = stdio_client(server_params)
            elif self.config.transport == "sse":
                self._transport = sse_client(url=self.config.url)
            else:
                raise ValueError(f"Unknown transport type: {self.config.transport}")

            read, write = await self._transport.__aenter__()
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()

            result = await self._session.list_tools()
            self._tools = [t.model_dump() for t in result.tools]
            self._tools_info = [
                MCPToolInfo(
                    server_name=self.config.name,
                    tool_name=t.name,
                    description=t.description or "",
                    input_schema=t.inputSchema if hasattr(t, "inputSchema") else {},
                )
                for t in result.tools
            ]
            self._connected = True
            logger.info("mcp_client_connected", server=self.config.name, tools=len(self._tools_info))
            if not ready.done():
                ready.set_result(self._tools_info)

            while True:
                command, payload, response = await self._command_queue.get()
                if command == "call_tool":
                    await self._handle_call_tool(payload, response)
                elif command == "disconnect":
                    disconnect_future = response
                    break
                else:
                    response.set_exception(ValueError(f"Unknown MCP client command: {command}"))
        except Exception as exc:
            if not ready.done():
                ready.set_exception(exc)
            if disconnect_future and not disconnect_future.done():
                disconnect_future.set_exception(exc)
            logger.warning("mcp_client_connection_failed", server=self.config.name, exc_info=True)
        finally:
            try:
                if self._session:
                    await self._session.__aexit__(None, None, None)
                if self._transport:
                    await self._transport.__aexit__(None, None, None)
            finally:
                self._session = None
                self._transport = None
                self._tools = []
                self._tools_info = []
                self._connected = False
                self._command_queue = None
                if disconnect_future and not disconnect_future.done():
                    disconnect_future.set_result(None)
                logger.info("mcp_client_disconnected", server=self.config.name)

    async def _handle_call_tool(self, payload: dict[str, Any], response: asyncio.Future) -> None:
        try:
            from mcp.types import CallToolResult, TextContent

            result: CallToolResult = await self._session.call_tool(
                payload["tool_name"],
                arguments=payload["arguments"],
            )
            parts = []
            for content in result.content:
                if isinstance(content, TextContent):
                    parts.append(content.text)
                else:
                    parts.append(str(content))
            response.set_result("\n".join(parts))
        except Exception as exc:
            response.set_exception(exc)

    async def disconnect(self) -> None:
        """Disconnect from the MCP server gracefully."""
        if not self._owner_task or self._owner_task.done():
            if self._owner_task:
                with suppress(Exception):
                    await self._owner_task
            self._tools = []
            self._tools_info = []
            self._connected = False
            self._command_queue = None
            self._owner_task = None
            return

        loop = asyncio.get_running_loop()
        response = loop.create_future()
        await self._command_queue.put(("disconnect", None, response))
        await response
        with suppress(Exception):
            await self._owner_task
        self._owner_task = None

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Invoke a tool on the MCP server and return the result as text."""
        if not self._connected:
            await self.connect()

        loop = asyncio.get_running_loop()
        response = loop.create_future()
        await self._command_queue.put((
            "call_tool",
            {"tool_name": tool_name, "arguments": arguments},
            response,
        ))
        return await response

    def list_tools(self) -> list[MCPToolInfo]:
        """Return discovered tool info (local cache, does not re-fetch)."""
        return self._tools_info

    def is_connected(self) -> bool:
        return self._connected
