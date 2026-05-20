"""Lane Queue — per-session serial execution to prevent concurrent request race conditions.

Each session key (e.g. "agent:user:admin1") gets its own lock. When a request arrives
for a session that's already processing, the new request waits until the current one
completes. This ensures deterministic message ordering and prevents state corruption.
"""

import asyncio
import time
import structlog

logger = structlog.get_logger()


class LaneQueue:
    """Per-session serial execution queue using asyncio locks.

    Session keys follow the design: agent:user:{user_id}, agent:{channel}:dm:{user_id},
    cron:{cron_id}, etc. Each key gets its own lock — requests for different sessions
    proceed independently, while requests for the same session are serialized.
    """

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._active_sessions: dict[str, float] = {}  # session_key -> last activity timestamp

    def _get_lock(self, session_key: str) -> asyncio.Lock:
        """Get or create a lock for a session key."""
        if session_key not in self._locks:
            self._locks[session_key] = asyncio.Lock()
        return self._locks[session_key]

    async def acquire(self, session_key: str) -> bool:
        """Acquire the lane lock for a session. Returns True if acquired immediately."""
        lock = self._get_lock(session_key)
        was_free = not lock.locked()
        await lock.acquire()
        self._active_sessions[session_key] = time.time()
        if not was_free:
            logger.info("lane_queue_wait", session_key=session_key, action="waited_for_lock")
        return was_free

    def release(self, session_key: str) -> None:
        """Release the lane lock for a session."""
        lock = self._locks.get(session_key)
        if lock and lock.locked():
            lock.release()
            logger.info("lane_queue_release", session_key=session_key)

    def is_locked(self, session_key: str) -> bool:
        """Check if a session is currently being processed."""
        lock = self._locks.get(session_key)
        return lock is not None and lock.locked()

    def get_active_sessions(self) -> dict[str, float]:
        """Get all currently active sessions with their last activity timestamp."""
        return {k: v for k, v in self._active_sessions.items() if self.is_locked(k)}

    def cleanup_stale(self, max_age_seconds: float = 300) -> int:
        """Remove locks for sessions that haven't been active for max_age_seconds."""
        removed = 0
        now = time.time()
        stale_keys = [k for k, ts in self._active_sessions.items()
                      if now - ts > max_age_seconds and not self.is_locked(k)]
        for key in stale_keys:
            self._locks.pop(key, None)
            self._active_sessions.pop(key, None)
            removed += 1
        if removed:
            logger.info("lane_queue_cleanup", removed=removed)
        return removed