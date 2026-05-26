"""Long-term memory: file-based storage (SOUL.md, USER.md, MEMORY.md, daily logs)."""

from pathlib import Path
from datetime import datetime
from typing import Optional

from harness.memory.types import MemoryFile, MemoryContext


class LongTermMemory:
    """Reads and writes per-user memory files. Files are the source of truth."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _user_dir(self, user_id: str) -> Path:
        d = self.base_dir / "users" / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _shared_dir(self) -> Path:
        d = self.base_dir / "users" / "shared"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def read_file(self, user_id: str, file: MemoryFile) -> str:
        """Read a memory file for a user. Falls back to shared if user file is empty."""
        user_path = self._user_dir(user_id) / file.value
        shared_path = self._shared_dir() / file.value

        content = ""
        if user_path.exists():
            content = user_path.read_text(encoding="utf-8")
        if not content and shared_path.exists():
            content = shared_path.read_text(encoding="utf-8")
        return content

    def write_file(self, user_id: str, file: MemoryFile, content: str) -> None:
        """Write (overwrite) a memory file for a user."""
        path = self._user_dir(user_id) / file.value
        path.write_text(content, encoding="utf-8")

    def append_file(self, user_id: str, file: MemoryFile, content: str) -> None:
        """Append content to a memory file."""
        path = self._user_dir(user_id) / file.value
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(existing + "\n" + content, encoding="utf-8")

    def write_daily_log(self, user_id: str, content: str, date: Optional[str] = None) -> None:
        """Write a daily log entry."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        memory_dir = self._user_dir(user_id) / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        log_path = memory_dir / f"{date}.md"
        existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        log_path.write_text(existing + "\n" + content, encoding="utf-8")

    def read_daily_log(self, user_id: str, date: Optional[str] = None) -> str:
        """Read daily log summary.

        Returns only the tail (~500 chars) of today's log as a lightweight
        recent-activity hint. Detailed historical context comes from mid-term
        (PG/pgvector semantic search), not from daily log bloat.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        path = self._user_dir(user_id) / "memory" / f"{date}.md"
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8")
        if len(content) > 500:
            content = "...(earlier) " + content[-500:]
        return content

    def read_daily_log_full(self, user_id: str, date: Optional[str] = None) -> str:
        """Read full daily log (for admin review, not for context injection)."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        path = self._user_dir(user_id) / "memory" / f"{date}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def init_user_workspace(self, user_id: str, soul_content: str = "", user_content: str = "") -> None:
        """Initialize a new user workspace with default files."""
        d = self._user_dir(user_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "memory").mkdir(exist_ok=True)

        if soul_content and not (d / MemoryFile.SOUL.value).exists():
            self.write_file(user_id, MemoryFile.SOUL, soul_content)
        if user_content and not (d / MemoryFile.USER.value).exists():
            self.write_file(user_id, MemoryFile.USER, user_content)
        if not (d / MemoryFile.MEMORY.value).exists():
            self.write_file(user_id, MemoryFile.MEMORY, "# Key Facts\n\n")

    def load_context(self, user_id: str) -> MemoryContext:
        """Load full memory context for a user (for before_model injection)."""
        return MemoryContext(
            soul_content=self.read_file(user_id, MemoryFile.SOUL),
            user_content=self.read_file(user_id, MemoryFile.USER),
            memory_content=self.read_file(user_id, MemoryFile.MEMORY),
            daily_log_content=self.read_daily_log(user_id),
        )


DEFAULT_SOUL = """# Agent Personality

You are an enterprise AI assistant for industrial and business scenarios.
- Be professional, concise, and practical
- Prioritize safety and accuracy in industrial contexts
- Proactively flag anomalies and risks
- Follow established procedures (Skills) when available
"""

DEFAULT_USER = """# User Profile

(User preferences will be learned over time through interaction.)
"""