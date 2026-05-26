"""Medium-term memory — PostgreSQL + pgvector async storage with full-text search."""

import uuid
from datetime import datetime, timedelta

import structlog

from harness.memory.types import MidTermSummaryType
from runtime.config import AgentConfig

logger = structlog.get_logger()


class MidTermMemory:
    """Manages per-user session summaries and knowledge in PostgreSQL.

    Uses asyncpg for async operations. Full-text search (ts_vector) for
    keyword-based retrieval. pgvector embedding column pre-defined for
    future semantic search (MVP: keyword search only).
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self._pool = None

    async def connect(self) -> None:
        """Create asyncpg connection pool and initialize schema."""
        try:
            import asyncpg
            from pgvector.asyncpg import register_vector
        except ImportError:
            logger.warning("mid_term_pg_packages_missing", detail="install asyncpg and pgvector")
            return

        self._pool = await asyncpg.create_pool(
            host=self.config.pg_host,
            port=self.config.pg_port,
            database=self.config.pg_database,
            user=self.config.pg_user,
            password=self.config.pg_password,
            min_size=self.config.pg_pool_min_size,
            max_size=self.config.pg_pool_max_size,
            init=register_vector,
        )
        await self._ensure_schema()
        logger.info("mid_term_connected", host=self.config.pg_host, database=self.config.pg_database)

    async def _ensure_schema(self) -> None:
        """Create table and indexes if they don't exist."""
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS mid_term_memory (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary_type TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    archived_at TIMESTAMPTZ,
                    metadata JSONB DEFAULT '{}',
                    embedding VECTOR(1536) DEFAULT NULL,
                    search_vector TSVECTOR GENERATED ALWAYS AS (
                        to_tsvector('simple', content)
                    ) STORED
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_mid_term_user_id ON mid_term_memory (user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_mid_term_search_vector ON mid_term_memory USING GIN (search_vector)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_mid_term_created_at ON mid_term_memory (created_at)")

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("mid_term_disconnected")

    async def write(
        self,
        user_id: str,
        content: str,
        summary_type: MidTermSummaryType,
        metadata: dict = None,
    ) -> str:
        """Write a mid-term memory entry. Returns the entry ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO mid_term_memory (user_id, content, summary_type, metadata)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                user_id,
                content,
                summary_type.value,
                metadata or {},
            )
            entry_id = str(row["id"])
            logger.info("mid_term_write", user_id=user_id, type=summary_type.value, entry_id=entry_id)
            return entry_id

    async def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        summary_types: list[MidTermSummaryType] | None = None,
    ) -> list[str]:
        """Search mid-term memory using full-text search (ts_vector).

        MVP: keyword-based search only. Future: combine with pgvector semantic search + RRF.
        """
        ts_query = " & ".join(query.split())

        async with self._pool.acquire() as conn:
            if summary_types:
                type_values = [t.value for t in summary_types]
                rows = await conn.fetch(
                    """
                    SELECT content, ts_rank_cd(search_vector, to_tsquery('simple', $1)) AS rank
                    FROM mid_term_memory
                    WHERE user_id = $2
                      AND archived_at IS NULL
                      AND search_vector @@ to_tsquery('simple', $1)
                      AND summary_type = ANY($4)
                    ORDER BY rank DESC, created_at DESC
                    LIMIT $3
                    """,
                    ts_query,
                    user_id,
                    top_k,
                    type_values,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT content, ts_rank_cd(search_vector, to_tsquery('simple', $1)) AS rank
                    FROM mid_term_memory
                    WHERE user_id = $2
                      AND archived_at IS NULL
                      AND search_vector @@ to_tsquery('simple', $1)
                    ORDER BY rank DESC, created_at DESC
                    LIMIT $3
                    """,
                    ts_query,
                    user_id,
                    top_k,
                )
            return [row["content"] for row in rows]

    async def search_recent(
        self,
        user_id: str,
        top_k: int = 5,
        days: int = 7,
        summary_types: list[MidTermSummaryType] | None = None,
    ) -> list[str]:
        """Retrieve recent memory entries (fallback when no clear keyword query)."""
        since = datetime.now() - timedelta(days=days)

        async with self._pool.acquire() as conn:
            if summary_types:
                type_values = [t.value for t in summary_types]
                rows = await conn.fetch(
                    """
                    SELECT content, created_at
                    FROM mid_term_memory
                    WHERE user_id = $1
                      AND archived_at IS NULL
                      AND created_at >= $2
                      AND summary_type = ANY($4)
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    user_id,
                    since,
                    top_k,
                    type_values,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT content, created_at
                    FROM mid_term_memory
                    WHERE user_id = $1
                      AND archived_at IS NULL
                      AND created_at >= $2
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    user_id,
                    since,
                    top_k,
                )
            return [row["content"] for row in rows]

    async def list_recent_users(self, hours: int = 1) -> list[str]:
        """Return distinct user IDs with activity in the last N hours."""
        since = datetime.now() - timedelta(hours=hours)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT user_id
                FROM mid_term_memory
                WHERE archived_at IS NULL
                  AND created_at >= $1
                """,
                since,
            )
            return [r["user_id"] for r in rows]

    async def archive_expired(self) -> int:
        """Archive entries older than retention_days. Returns count archived."""
        cutoff = datetime.now() - timedelta(days=self.config.mid_term_retention_days)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE mid_term_memory
                SET archived_at = NOW()
                WHERE archived_at IS NULL
                  AND created_at < $1
                """,
                cutoff,
            )
            count = int(result.split()[-1]) if result else 0
            if count:
                logger.info("mid_term_archive_expired", count=count)
            return count