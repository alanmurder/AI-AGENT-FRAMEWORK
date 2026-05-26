"""Sandbox subsystem - pluggable isolation for files, shell, and Python."""

from harness.sandbox.manager import SandboxManager
from harness.sandbox.types import SandboxResult

__all__ = ["SandboxManager", "SandboxResult"]
