"""Web channel adapter — handles WebSocket and REST API communication."""

import json
from datetime import datetime

from gateway.adapters.base import ChannelAdapter
from gateway.types import StandardMessage, AgentResponse, ChannelType


class WebAdapter(ChannelAdapter):
    """Web UI channel adapter — WebSocket + REST API."""

    channel_type = ChannelType.WEB

    async def connect(self) -> bool:
        return True  # Web is always "connected" via HTTP/WebSocket

    async def receive(self) -> list[StandardMessage]:
        # Web messages come directly through API endpoints, not via polling
        return []

    async def send(self, user_id: str, response: AgentResponse) -> bool:
        # Sending handled directly by FastAPI response, not through adapter
        return True

    async def disconnect(self) -> bool:
        return True

    def normalize(self, raw: dict) -> StandardMessage:
        """Convert web request body to StandardMessage."""
        return StandardMessage(
            user_id=raw.get("user_id", "anonymous"),
            channel=ChannelType.WEB,
            content=raw.get("content", ""),
            metadata=raw.get("metadata", {}),
            timestamp=raw.get("timestamp", datetime.now().isoformat()),
        )

    def format_response(self, response: AgentResponse) -> dict:
        """Convert AgentResponse to web JSON format."""
        return {
            "content": response.content,
            "tool_calls": response.tool_calls,
            "metadata": response.metadata,
        }