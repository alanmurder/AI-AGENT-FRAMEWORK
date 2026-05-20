"""Memory Manager — coordinates four-layer memory operations."""

from langchain_core.language_models import BaseChatModel

from harness.memory.long_term import LongTermMemory, DEFAULT_SOUL, DEFAULT_USER
from harness.memory.short_term import ShortTermMemory
from harness.memory.evolution import MemoryEvolution
from harness.memory.types import MemoryContext, MemoryFile, MidTermSummaryType
from runtime.config import AgentConfig


class MemoryManager:
    """Central coordinator for all memory operations."""

    def __init__(self, config: AgentConfig, mini_model: BaseChatModel | None = None):
        self.config = config
        self.long_term = LongTermMemory(config.get_memory_base_dir())
        self.short_term = ShortTermMemory(config)
        self.mid_term = None  # Optional MidTermMemory, created on connect
        self.evolution = MemoryEvolution(mini_model) if mini_model else None

    async def connect_mid_term(self) -> None:
        """Connect to PostgreSQL for mid-term memory. Call on gateway startup."""
        from harness.memory.mid_term import MidTermMemory
        self.mid_term = MidTermMemory(self.config)
        try:
            await self.mid_term.connect()
        except Exception as e:
            # PG unavailable — gracefully degrade
            import structlog
            structlog.get_logger().warning("mid_term_connect_failed", error=str(e))
            self.mid_term = None

    async def disconnect_mid_term(self) -> None:
        """Disconnect from PostgreSQL. Call on gateway shutdown."""
        if self.mid_term:
            await self.mid_term.disconnect()
            self.mid_term = None

    def init_user(self, user_id: str) -> None:
        """Initialize workspace for a new user."""
        self.long_term.init_user_workspace(
            user_id,
            soul_content=DEFAULT_SOUL,
            user_content=DEFAULT_USER,
        )

    def load_context(self, user_id: str) -> MemoryContext:
        """Load full memory context for injection into agent prompt."""
        return self.long_term.load_context(user_id)

    def save_memory(self, user_id: str, memory_type: MemoryFile, content: str) -> None:
        """Save content to a long-term memory file."""
        self.long_term.write_file(user_id, memory_type, content)

    def append_memory(self, user_id: str, memory_type: MemoryFile, content: str) -> None:
        """Append content to a long-term memory file."""
        self.long_term.append_file(user_id, memory_type, content)

    def log_daily(self, user_id: str, content: str) -> None:
        """Write a daily log entry."""
        self.long_term.write_daily_log(user_id, content)

    async def get_session_messages(self, user_id: str, session_id: str) -> list[dict]:
        """Get short-term session messages."""
        return await self.short_term.get_messages(user_id, session_id)

    async def add_session_message(self, user_id: str, session_id: str, message: dict) -> None:
        """Add a message to short-term session."""
        await self.short_term.add_message(user_id, session_id, message)

    async def write_mid_term(
        self, user_id: str, content: str,
        summary_type: MidTermSummaryType, metadata: dict = None,
    ) -> str | None:
        """Write to mid-term memory. Returns entry ID or None if PG not connected."""
        if self.mid_term:
            try:
                return await self.mid_term.write(user_id, content, summary_type, metadata)
            except Exception:
                return None
        return None

    async def search_mid_term(self, user_id: str, query: str, top_k: int = 5) -> list[str]:
        """Search mid-term memory. Returns empty list if PG not connected."""
        if self.mid_term:
            try:
                return await self.mid_term.search(user_id, query, top_k)
            except Exception:
                return []
        return []

    async def search_mid_term_recent(self, user_id: str, top_k: int = 3, days: int = 7) -> list[str]:
        """Get recent mid-term memory entries."""
        if self.mid_term:
            try:
                return await self.mid_term.search_recent(user_id, top_k, days)
            except Exception:
                return []
        return []

    def extract_and_save(self, user_id: str, conversation_summary: str) -> None:
        """L1 memory evolution: extract preferences/facts from conversation and save."""
        if self.evolution:
            result = self.evolution.extract(conversation_summary)
            preferences = result["preferences"]
            facts = result["facts"]
        else:
            preferences = []
            facts = []

        if preferences:
            pref_text = "\n".join(f"- {p}" for p in preferences)
            self.append_memory(user_id, MemoryFile.USER, f"\n## Extracted Preferences\n{pref_text}")

        if facts:
            fact_text = "\n".join(f"- {f}" for f in facts)
            self.append_memory(user_id, MemoryFile.MEMORY, f"\n## Extracted Facts\n{fact_text}")

        # Always log to daily
        self.log_daily(user_id, conversation_summary)