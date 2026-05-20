"""Context management type definitions."""

from dataclasses import dataclass


@dataclass
class ContextConfig:
    compression_threshold: int = 4000
    flush_threshold: int = 60000
    max_flush_per_session: int = 1
    placeholder_threshold: int = 2000
    keep_recent_messages: int = 20