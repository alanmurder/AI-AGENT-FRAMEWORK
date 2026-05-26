"""Sandbox abstractions and shared result types."""

from dataclasses import dataclass, field


@dataclass
class SandboxResult:
    """Normalized result returned by all sandbox backends."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    duration_ms: float = 0.0
    backend: str = ""
    session_id: str = ""
    metadata: dict = field(default_factory=dict)


class SandboxError(Exception):
    """Base class for sandbox errors."""


class SandboxUnavailableError(SandboxError):
    """Raised when sandbox execution is required but no backend is available."""


class SandboxPathError(SandboxError):
    """Raised when a file path escapes the sandbox workspace."""

