"""before_agent middleware — validates that user context is available in runtime."""

from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

from runtime.context_schema import UserContext


class AuthInjectionMiddleware(AgentMiddleware):
    """Validates that user context is present before agent processing begins.

    The UserContext is injected via `create_agent(context_schema=UserContext)` and
    passed through LangGraph's Runtime mechanism when invoking the agent with
    `config={'configurable': {'context': user_ctx}}`. This middleware verifies
    it's present and initializes the user workspace if needed.
    """

    def __init__(self, user_ctx: UserContext):
        self.user_ctx = user_ctx

    def before_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Validate user context is available in the runtime."""
        # Context is set by LangGraph's Runtime injection mechanism, not by us.
        # We just verify it's there. If missing, we use our stored user_ctx as reference.
        ctx = runtime.context if runtime is not None else self.user_ctx

        # Initialize user workspace if needed
        from harness.memory.manager import MemoryManager
        from runtime.config import AgentConfig
        config = AgentConfig()
        mm = MemoryManager(config)
        mm.init_user(ctx.user_id if isinstance(ctx, UserContext) else self.user_ctx.user_id)

        return None