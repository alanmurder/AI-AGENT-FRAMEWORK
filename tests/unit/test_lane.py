"""Lane Queue tests — per-session serial execution."""

import asyncio
import pytest
from gateway.lane import LaneQueue


@pytest.fixture
def lane():
    return LaneQueue()


class TestLaneQueue:
    @pytest.mark.asyncio
    async def test_acquire_and_release(self, lane):
        key = "agent:user:admin1"
        was_free = await lane.acquire(key)
        assert was_free is True
        assert lane.is_locked(key)
        lane.release(key)
        assert not lane.is_locked(key)

    @pytest.mark.asyncio
    async def test_serial_execution(self, lane):
        """Two concurrent requests for the same session should be serialized."""
        key = "agent:user:user1"
        results = []

        async def task(name, delay=0.05):
            await lane.acquire(key)
            results.append(f"{name}_start")
            await asyncio.sleep(delay)
            results.append(f"{name}_end")
            lane.release(key)

        # Launch both concurrently
        await asyncio.gather(task("A"), task("B"))

        # Verify serialization: one completes before the other starts
        # Possible orderings: A_start, A_end, B_start, B_end OR B_start, B_end, A_start, A_end
        assert len(results) == 4
        # Check that start and end of same task are adjacent (serialized)
        idx_a_start = results.index("A_start")
        idx_a_end = results.index("A_end")
        idx_b_start = results.index("B_start")
        idx_b_end = results.index("B_end")
        # Each task's start and end should be consecutive
        assert abs(idx_a_start - idx_a_end) == 1
        assert abs(idx_b_start - idx_b_end) == 1

    @pytest.mark.asyncio
    async def test_independent_sessions(self, lane):
        """Different session keys should execute independently (concurrently)."""
        results = []

        async def task(key, name, delay=0.05):
            await lane.acquire(key)
            results.append(f"{name}_start")
            await asyncio.sleep(delay)
            results.append(f"{name}_end")
            lane.release(key)

        await asyncio.gather(
            task("agent:user:user1", "A"),
            task("agent:user:user2", "B"),
        )

        # Both should complete — order doesn't matter
        assert len(results) == 4
        assert "A_start" in results
        assert "B_start" in results

    @pytest.mark.asyncio
    async def test_is_locked(self, lane):
        key = "agent:user:test1"
        assert not lane.is_locked(key)
        await lane.acquire(key)
        assert lane.is_locked(key)
        lane.release(key)
        assert not lane.is_locked(key)

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, lane):
        await lane.acquire("agent:user:active1")
        await lane.acquire("agent:user:active2")
        active = lane.get_active_sessions()
        assert len(active) == 2
        lane.release("agent:user:active1")
        lane.release("agent:user:active2")

    @pytest.mark.asyncio
    async def test_cleanup_stale(self, lane):
        # Acquire and release a lock (leaves stale entry in _active_sessions)
        await lane.acquire("agent:user:stale1")
        lane.release("agent:user:stale1")

        # After release, the lock is not held, and with no new activity it's stale
        # Wait a bit then cleanup with very small max_age
        await asyncio.sleep(0.1)
        removed = lane.cleanup_stale(max_age_seconds=0.05)
        assert removed >= 1