"""MCP type definitions."""

from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server connection."""

    name: str
    transport: str = "stdio"  # "stdio" | "sse"
    command: str = ""  # for stdio transport
    args: list[str] = field(default_factory=list)
    url: str = ""  # for sse transport
    enabled: bool = True
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class MCPToolInfo:
    """Information about a discovered MCP tool."""

    server_name: str
    tool_name: str
    description: str
    input_schema: dict = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        """Return 'server:tool' format — used in RBAC config and agent profiles."""
        return f"{self.server_name}:{self.tool_name}"

    @property
    def func_name(self) -> str:
        """Return 'mcp__server__tool' format — used as LangChain tool function name."""
        return f"mcp__{self.server_name}__{self.tool_name}"
