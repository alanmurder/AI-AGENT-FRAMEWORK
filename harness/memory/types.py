"""Memory system type definitions."""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


class MemoryType(str, Enum):
    LONG_TERM = "long_term"
    MID_TERM = "mid_term"
    SHORT_TERM = "short_term"
    WORKING = "working"


class MidTermSummaryType(str, Enum):
    SESSION_SUMMARY = "session_summary"
    DAILY_LOG = "daily_log"
    FACT = "fact"
    TASK_HISTORY = "task_history"


class MemoryFile(str, Enum):
    SOUL = "SOUL.md"
    USER = "USER.md"
    MEMORY = "MEMORY.md"


@dataclass
class MemoryEntry:
    content: str
    source: MemoryType
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


@dataclass
class MemoryContext:
    soul_content: str = ""
    user_content: str = ""
    memory_content: str = ""
    daily_log_content: str = ""
    mid_term_results: list[str] = field(default_factory=list)

    def to_prompt_section(self) -> str:
        parts = []
        if self.soul_content:
            parts.append(f"## Agent Personality (SOUL.md)\n{self.soul_content}")
        if self.user_content:
            parts.append(f"## User Profile (USER.md)\n{self.user_content}")
        if self.memory_content:
            parts.append(f"## Key Facts (MEMORY.md)\n{self.memory_content}")
        if self.daily_log_content:
            parts.append(f"## Recent Context\n{self.daily_log_content}")
        if self.mid_term_results:
            parts.append(f"## Related History\n" + "\n".join(self.mid_term_results))
        return "\n\n".join(parts) if parts else ""