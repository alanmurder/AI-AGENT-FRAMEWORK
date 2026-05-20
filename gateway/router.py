"""Agent router — routes messages to appropriate agent instances."""

from runtime.context_schema import UserContext, UserRole
from gateway.types import ChannelType, StandardMessage
from harness.expert.registry import AgentRegistry


class GatewayRouter:
    """Routes incoming messages to the appropriate agent."""

    def __init__(self, registry: AgentRegistry | None = None):
        self.registry = registry or AgentRegistry()

    def route(self, message: StandardMessage, user_ctx: UserContext) -> str:
        """Determine which agent should handle this message.

        If user_ctx.agent_id is set and the expert exists in registry → route to expert.
        Otherwise → route to default agent.
        """
        if user_ctx.agent_id and self.registry.get(user_ctx.agent_id):
            return user_ctx.agent_id
        return "default"


class SessionManager:
    """Manages session keys and state."""

    def create_session_key(self, channel: ChannelType, user_id: str, group_id: str = None, expert_id: str = None) -> str:
        """Generate a session key based on channel, user, and optional expert."""
        if expert_id:
            return f"agent:{expert_id}:user:{user_id}"
        if group_id:
            return f"agent:{channel.value}:group:{group_id}"
        elif channel == ChannelType.WEB:
            return f"agent:user:{user_id}"
        else:
            return f"agent:{channel.value}:dm:{user_id}"

    def create_cron_session_key(self, cron_id: str) -> str:
        return f"cron:{cron_id}"

    def create_subagent_session_key(self, task_id: str) -> str:
        return f"agent:subagent:{task_id}"