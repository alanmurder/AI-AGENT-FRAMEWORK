"""wrap_model_call middleware — filters available tools based on user role."""

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from runtime.context_schema import UserContext, UserRole
from harness.security.rbac import get_role_tool_access, get_role_mcp_tool_access

# Reference to MCP manager (set at startup by gateway server)
_mcp_manager = None


def set_mcp_manager(manager) -> None:
    """Register the MCP manager for tool matching in filter middleware."""
    global _mcp_manager
    _mcp_manager = manager


def _is_mcp_tool(tool_name: str) -> bool:
    """Check if a tool name is an MCP tool (prefix 'mcp__')."""
    return tool_name.startswith("mcp__")


def _mcp_full_name(tool_name: str) -> str:
    """Convert 'mcp__server__tool' to 'server:tool' for RBAC matching."""
    rest = tool_name[5:]
    parts = rest.split("__", 1)
    if len(parts) == 2:
        return f"{parts[0]}:{parts[1]}"
    return tool_name


def _match_mcp_allowed(full_name: str, allowed: list[str]) -> bool:
    """Check if a 'server:tool' name matches the allowed list (supports 'server:*' and '*')."""
    for pattern in allowed:
        if pattern == "*":
            return True
        if pattern == full_name:
            return True
        if pattern.endswith(":*"):
            prefix = pattern[:-2]
            if full_name.startswith(prefix + ":"):
                return True
    return False


class ToolFilterMiddleware(AgentMiddleware):
    """Filters tools available to the model based on user role."""

    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
        """Remove tools not allowed for the current user's role."""
        role_tool_access = get_role_tool_access()
        role_mcp_access = get_role_mcp_tool_access()

        if request.runtime is None or request.runtime.context is None:
            allowed_tools = role_tool_access[UserRole.VIEWER]
            allowed_mcp = role_mcp_access.get(UserRole.VIEWER, [])
        else:
            user_ctx: UserContext = request.runtime.context
            allowed_tools = role_tool_access.get(user_ctx.role, role_tool_access[UserRole.VIEWER])
            allowed_mcp = role_mcp_access.get(user_ctx.role, [])

            if user_ctx.permissions:
                allowed_tools = user_ctx.permissions

        # Filter static tools and MCP tools
        filtered = []
        for t in request.tools:
            if _is_mcp_tool(t.name):
                full_name = _mcp_full_name(t.name)
                if _match_mcp_allowed(full_name, allowed_mcp):
                    filtered.append(t)
            elif t.name in allowed_tools:
                filtered.append(t)

        updated = request.override(tools=filtered)
        return handler(updated)