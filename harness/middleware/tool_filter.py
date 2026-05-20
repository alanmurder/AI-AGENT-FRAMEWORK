"""wrap_model_call middleware — filters available tools based on user role."""

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from runtime.context_schema import UserContext, UserRole
from harness.security.rbac import get_role_tool_access


class ToolFilterMiddleware(AgentMiddleware):
    """Filters tools available to the model based on user role."""

    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
        """Remove tools not allowed for the current user's role."""
        role_tool_access = get_role_tool_access()

        if request.runtime is None or request.runtime.context is None:
            # No context — use most restrictive defaults (viewer)
            allowed_tools = role_tool_access[UserRole.VIEWER]
        else:
            user_ctx: UserContext = request.runtime.context
            allowed_tools = role_tool_access.get(user_ctx.role, role_tool_access[UserRole.VIEWER])

            # Also check explicit permissions list (for dynamic overrides)
            if user_ctx.permissions:
                allowed_tools = user_ctx.permissions

        # Filter tools
        filtered_tools = [t for t in request.tools if t.name in allowed_tools]
        updated = request.override(tools=filtered_tools)
        return handler(updated)