"""Unit tests for Mid-term Memory (PostgreSQL) — mock-based, no PG dependency."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from harness.memory.mid_term import MidTermMemory
from harness.memory.types import MidTermSummaryType
from harness.memory.manager import MemoryManager
from runtime.config import AgentConfig


@pytest.fixture
def config():
    return AgentConfig(
        pg_host="localhost",
        pg_port=5432,
        pg_database="test_db",
        pg_user="test_user",
        pg_password="test_pass",
        mid_term_retention_days=30,
        mid_term_search_top_k=5,
    )


@pytest.fixture
def mid_term(config):
    mm = MidTermMemory(config)
    mm._pool = AsyncMock()
    return mm


def _mock_pool_acquire(mock_conn):
    """Helper: set up mock pool.acquire() as async context manager."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


class TestMidTermSummaryType:
    def test_values(self):
        assert MidTermSummaryType.SESSION_SUMMARY == "session_summary"
        assert MidTermSummaryType.DAILY_LOG == "daily_log"
        assert MidTermSummaryType.FACT == "fact"
        assert MidTermSummaryType.TASK_HISTORY == "task_history"


class TestMidTermMemoryMocked:
    @pytest.mark.asyncio
    async def test_write_returns_id(self, mid_term):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"id": "test-uuid-123"})
        mid_term._pool.acquire = MagicMock(return_value=_mock_pool_acquire(mock_conn))

        result = await mid_term.write("user1", "Test content", MidTermSummaryType.SESSION_SUMMARY)
        assert result == "test-uuid-123"

    @pytest.mark.asyncio
    async def test_write_with_metadata(self, mid_term):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"id": "meta-uuid"})
        mid_term._pool.acquire = MagicMock(return_value=_mock_pool_acquire(mock_conn))

        result = await mid_term.write(
            "user1", "Content", MidTermSummaryType.FACT,
            metadata={"source": "evolution"},
        )
        assert result == "meta-uuid"

    @pytest.mark.asyncio
    async def test_search_returns_content(self, mid_term):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"content": "Previous session about production line", "rank": 0.5},
            {"content": "Daily log about kiln temperature", "rank": 0.3},
        ])
        mid_term._pool.acquire = MagicMock(return_value=_mock_pool_acquire(mock_conn))

        results = await mid_term.search("user1", "production kiln", top_k=5)
        assert len(results) == 2
        assert "production line" in results[0]

    @pytest.mark.asyncio
    async def test_search_with_type_filter(self, mid_term):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"content": "Fact extracted: kiln runs at 85%", "rank": 0.6},
        ])
        mid_term._pool.acquire = MagicMock(return_value=_mock_pool_acquire(mock_conn))

        results = await mid_term.search(
            "user1", "kiln", top_k=5,
            summary_types=[MidTermSummaryType.FACT],
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_recent(self, mid_term):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"content": "Recent session about maintenance", "created_at": datetime.now()},
        ])
        mid_term._pool.acquire = MagicMock(return_value=_mock_pool_acquire(mock_conn))

        results = await mid_term.search_recent("user1", top_k=5, days=7)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_archive_expired(self, mid_term):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 3")
        mid_term._pool.acquire = MagicMock(return_value=_mock_pool_acquire(mock_conn))

        count = await mid_term.archive_expired()
        assert count == 3

    @pytest.mark.asyncio
    async def test_archive_expired_none(self, mid_term):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 0")
        mid_term._pool.acquire = MagicMock(return_value=_mock_pool_acquire(mock_conn))

        count = await mid_term.archive_expired()
        assert count == 0

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self, config):
        mm = MidTermMemory(config)

        # Create mock pool that behaves like asyncpg.Pool
        mock_pool = AsyncMock()
        mock_pool.close = AsyncMock(return_value=None)

        # Mock _ensure_schema by patching pool acquire
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=None)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_conn)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=cm)

        # Directly inject mock pool and verify
        mm._pool = mock_pool
        await mm._ensure_schema()  # Should work with mock
        assert mm._pool is not None

        await mm.disconnect()
        assert mm._pool is None


class TestMemoryManagerMidTerm:
    @pytest.mark.asyncio
    async def test_write_mid_term_delegates(self, config):
        mm = MemoryManager(config)

        # Create a mock MidTermMemory
        mock_mid = AsyncMock()
        mock_mid.write = AsyncMock(return_value="entry-123")
        mm.mid_term = mock_mid

        result = await mm.write_mid_term("user1", "content", MidTermSummaryType.SESSION_SUMMARY)
        assert result == "entry-123"

    @pytest.mark.asyncio
    async def test_write_mid_term_none_when_no_pg(self, config):
        mm = MemoryManager(config)
        mm.mid_term = None

        result = await mm.write_mid_term("user1", "content", MidTermSummaryType.SESSION_SUMMARY)
        assert result is None

    @pytest.mark.asyncio
    async def test_search_mid_term_delegates(self, config):
        mm = MemoryManager(config)

        mock_mid = AsyncMock()
        mock_mid.search = AsyncMock(return_value=["result1", "result2"])
        mm.mid_term = mock_mid

        results = await mm.search_mid_term("user1", "query", top_k=5)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_mid_term_empty_when_no_pg(self, config):
        mm = MemoryManager(config)
        mm.mid_term = None

        results = await mm.search_mid_term("user1", "query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_mid_term_recent_delegates(self, config):
        mm = MemoryManager(config)

        mock_mid = AsyncMock()
        mock_mid.search_recent = AsyncMock(return_value=["recent1"])
        mm.mid_term = mock_mid

        results = await mm.search_mid_term_recent("user1", top_k=3, days=7)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_mid_term_recent_empty_when_no_pg(self, config):
        mm = MemoryManager(config)
        mm.mid_term = None

        results = await mm.search_mid_term_recent("user1")
        assert results == []

    @pytest.mark.asyncio
    async def test_connect_mid_term_success(self, config):
        mm = MemoryManager(config)

        with patch("harness.memory.mid_term.MidTermMemory") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(return_value=None)
            mock_cls.return_value = mock_instance

            await mm.connect_mid_term()
            assert mm.mid_term is not None

    @pytest.mark.asyncio
    async def test_connect_mid_term_failure_graceful(self, config):
        mm = MemoryManager(config)

        with patch("harness.memory.mid_term.MidTermMemory") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(side_effect=Exception("PG unavailable"))
            mock_cls.return_value = mock_instance

            await mm.connect_mid_term()
            assert mm.mid_term is None  # Gracefully degraded

    @pytest.mark.asyncio
    async def test_disconnect_mid_term(self, config):
        mm = MemoryManager(config)
        mm.mid_term = AsyncMock()
        mm.mid_term.disconnect = AsyncMock(return_value=None)

        await mm.disconnect_mid_term()
        assert mm.mid_term is None