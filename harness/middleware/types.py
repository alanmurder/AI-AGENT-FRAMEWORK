"""Middleware integration types."""

from dataclasses import dataclass
from harness.memory.types import MemoryContext
from runtime.context_schema import UserContext


@dataclass
class MiddlewareContext:
    """Context passed through the middleware chain."""
    user: UserContext
    memory: MemoryContext
    skill_manifest: str = ""
    flush_triggered: bool = False