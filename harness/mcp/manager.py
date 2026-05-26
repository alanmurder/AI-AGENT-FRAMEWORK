"""MCPManager — orchestrates MCP server connections, tool registration, and role filtering."""

import os
import asyncio
import structlog
from collections.abc import Callable
from pathlib import Path

from langchain.tools import tool as langchain_tool

from runtime.context_schema import UserRole
from harness.mcp.types import MCPServerConfig, MCPToolInfo
from harness.mcp.config import MCPServerStore
from harness.mcp.client import MCPClient

logger = structlog.get_logger()


class MCPManager:
    """Orchestrates all MCP server connections and wraps tools for LangChain agents."""

    def __init__(self, project_root: Path | str | None = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent
        elif isinstance(project_root, str):
            project_root = Path(project_root)
        self._project_root = project_root
        self._store = MCPServerStore(project_root)
        self._clients: dict[str, MCPClient] = {}
        self._tools: dict[str, Callable] = {}  # func_name -> langchain tool callable
        self._tools_info: dict[str, MCPToolInfo] = {}  # func_name -> tool info

    async def initialize(self) -> None:
        """Connect to all enabled MCP servers and discover their tools."""
        servers = self._store.list_servers()
        for server_config in servers:
            if server_config.enabled:
                try:
                    await self._connect_server(server_config)
                except Exception:
                    logger.warning("mcp_init_connect_failed", server=server_config.name, exc_info=True)
        logger.info("mcp_manager_initialized", connected=len(self._clients), tools=len(self._tools))

    async def shutdown(self) -> None:
        """Disconnect all MCP servers gracefully."""
        for name in list(self._clients.keys()):
            try:
                await self.disconnect_server(name)
            except Exception:
                logger.warning("mcp_shutdown_failed", server=name, exc_info=True)
        logger.info("mcp_manager_shutdown")

    async def add_server(self, config: MCPServerConfig) -> list[MCPToolInfo]:
        """Persist config and connect if enabled."""
        self._store.save_server(config)
        if config.enabled:
            return await self._connect_server(config)
        return []

    async def remove_server(self, name: str) -> bool:
        """Disconnect and remove a server config."""
        if name in self._clients:
            await self.disconnect_server(name)
        return self._store.delete_server(name)

    async def toggle_server(self, name: str, enabled: bool) -> list[MCPToolInfo]:
        """Enable/disable a server, connecting or disconnecting as needed."""
        config = self._store.get_server(name)
        if not config:
            raise ValueError(f"Server not found: {name}")
        config.enabled = enabled
        self._store.save_server(config)
        if enabled:
            return await self._connect_server(config)
        else:
            await self.disconnect_server(name)
            return []

    async def connect_server(self, name: str) -> list[MCPToolInfo]:
        """Reconnect a server by name."""
        config = self._store.get_server(name)
        if not config:
            raise ValueError(f"Server not found: {name}")
        return await self._connect_server(config)

    async def disconnect_server(self, name: str) -> None:
        """Disconnect a single server and remove its tools."""
        client = self._clients.pop(name, None)
        if client:
            await client.disconnect()
            # Remove all tools from this server
            prefix = f"mcp__{name}__"
            for func_name in list(self._tools.keys()):
                if func_name.startswith(prefix):
                    del self._tools[func_name]
                    del self._tools_info[func_name]

    def get_tools_for_role(self, role: UserRole, role_mcp_access: dict[UserRole, list[str]]) -> list[Callable]:
        """Return LangChain tool functions filtered by role's MCP tool access."""
        from harness.security.rbac import get_role_mcp_tool_access as _load_access

        allowed = role_mcp_access.get(role, [])
        if not allowed:
            allowed = _load_access().get(role, [])

        result = []
        for func_name, tool_fn in self._tools.items():
            full_name = func_name_to_full_name(func_name)
            if _match_allowed(full_name, allowed):
                result.append(tool_fn)
        return result

    def get_all_tools(self) -> list[Callable]:
        """Return all discovered MCP tools as LangChain callables."""
        return list(self._tools.values())

    def get_server_tools(self, server_name: str) -> list[MCPToolInfo]:
        """Return discovered tools for a specific server."""
        prefix = f"mcp__{server_name}__"
        return [info for func_name, info in self._tools_info.items() if func_name.startswith(prefix)]

    def get_all_tools_info(self) -> list[MCPToolInfo]:
        """Return all discovered tool info."""
        return list(self._tools_info.values())

    def list_servers(self) -> list[MCPServerConfig]:
        return self._store.list_servers()

    def get_server(self, name: str) -> MCPServerConfig | None:
        return self._store.get_server(name)

    # ── internal ──

    async def _connect_server(self, config: MCPServerConfig) -> list[MCPToolInfo]:
        if config.name in self._clients:
            await self.disconnect_server(config.name)

        client = MCPClient(config)
        tools_info = await client.connect()
        self._clients[config.name] = client

        for info in tools_info:
            fn = self._create_langchain_tool(info, client)
            self._tools[info.func_name] = fn
            self._tools_info[info.func_name] = info

        logger.info("mcp_server_connected", server=config.name, tools=len(tools_info))
        return tools_info

    def _create_langchain_tool(self, info: MCPToolInfo, client: MCPClient) -> Callable:
        """Wrap an MCP tool as a LangChain @tool function."""

        import asyncio

        @langchain_tool(info.func_name, description=f"[MCP:{info.server_name}] {info.description}")
        def _wrapper(**kwargs) -> str:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                future = concurrent.futures.Future()

                async def _run():
                    try:
                        result = await client.call_tool(info.tool_name, kwargs)
                        future.set_result(result)
                    except Exception as e:
                        future.set_exception(e)

                loop.call_soon_threadsafe(asyncio.ensure_future, _run())
                return future.result(timeout=60)
            else:
                return loop.run_until_complete(client.call_tool(info.tool_name, kwargs))

        _wrapper.__name__ = info.func_name
        return _wrapper


def func_name_to_full_name(func_name: str) -> str:
    """Convert 'mcp__server__tool' to 'server:tool'."""
    if func_name.startswith("mcp__"):
        rest = func_name[5:]
        parts = rest.split("__", 1)
        if len(parts) == 2:
            return f"{parts[0]}:{parts[1]}"
    return func_name


def _match_allowed(full_name: str, allowed: list[str]) -> bool:
    """Check if a 'server:tool' name matches the allowed list (supports wildcards)."""
    from harness.security.rbac import mcp_tool_allowed

    return mcp_tool_allowed(full_name, allowed)
