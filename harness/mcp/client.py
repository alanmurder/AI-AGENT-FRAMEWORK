"""MCPClient — manages a single MCP server connection and tool discovery."""

import os
import asyncio
import structlog

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

    async def connect(self) -> list[MCPToolInfo]:
        """Connect to the MCP server and discover its tools."""
        if self._connected:
            return self._tools_info

        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.sse import sse_client

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
        return self._tools_info

    async def disconnect(self) -> None:
        """Disconnect from the MCP server gracefully."""
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._transport:
            await self._transport.__aexit__(None, None, None)
            self._transport = None
        self._tools = []
        self._tools_info = []
        self._connected = False
        logger.info("mcp_client_disconnected", server=self.config.name)

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Invoke a tool on the MCP server and return the result as text."""
        if not self._connected:
            await self.connect()

        from mcp.types import CallToolResult, TextContent

        result: CallToolResult = await self._session.call_tool(tool_name, arguments=arguments)
        parts = []
        for content in result.content:
            if isinstance(content, TextContent):
                parts.append(content.text)
            else:
                parts.append(str(content))
        return "\n".join(parts)

    def list_tools(self) -> list[MCPToolInfo]:
        """Return discovered tool info (local cache, does not re-fetch)."""
        return self._tools_info

    def is_connected(self) -> bool:
        return self._connected
