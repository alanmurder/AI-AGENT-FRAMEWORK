"""Short-term memory: async Redis-based session cache."""

import json
import redis.asyncio as aioredis
from typing import Optional

from runtime.config import AgentConfig


class ShortTermMemory:
    """Manages per-user session data in Redis (async)."""

    def __init__(self, config: AgentConfig):
        self.redis = aioredis.from_url(config.redis_url, decode_responses=True)
        self.session_ttl = 3600

    def _key(self, user_id: str, session_id: str, subkey: str) -> str:
        return f"agent:{user_id}:{session_id}:{subkey}"

    async def get_messages(self, user_id: str, session_id: str) -> list[dict]:
        """Get session message history."""
        key = self._key(user_id, session_id, "messages")
        data = await self.redis.get(key)
        return json.loads(data) if data else []

    async def add_message(self, user_id: str, session_id: str, message: dict) -> None:
        """Append a message to session history."""
        key = self._key(user_id, session_id, "messages")
        messages = await self.get_messages(user_id, session_id)
        messages.append(message)
        await self.redis.setex(key, self.session_ttl, json.dumps(messages))

    async def get_state(self, user_id: str, session_id: str) -> dict:
        """Get session state (temp variables, etc.)."""
        key = self._key(user_id, session_id, "state")
        data = await self.redis.get(key)
        return json.loads(data) if data else {}

    async def set_state(self, user_id: str, session_id: str, state: dict) -> None:
        """Set session state."""
        key = self._key(user_id, session_id, "state")
        await self.redis.setex(key, self.session_ttl, json.dumps(state))

    async def clear_session(self, user_id: str, session_id: str) -> None:
        """Clear all session data."""
        pattern = self._key(user_id, session_id, "*")
        async for key in self.redis.scan_iter(pattern):
            await self.redis.delete(key)

    async def set_flush_triggered(self, user_id: str, session_id: str) -> None:
        """Mark that pre-compression flush has been triggered for this session."""
        key = self._key(user_id, session_id, "flush_triggered")
        await self.redis.setex(key, self.session_ttl, "1")

    async def is_flush_triggered(self, user_id: str, session_id: str) -> bool:
        """Check if pre-compression flush has already been triggered."""
        key = self._key(user_id, session_id, "flush_triggered")
        return await self.redis.exists(key) > 0