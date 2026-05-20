"""Security system type definitions."""

from dataclasses import dataclass
from enum import Enum


class ApprovalLevel(str, Enum):
    L0 = "L0"  # string match
    L1 = "L1"  # regex match
    L2 = "L2"  # whitelist
    L3 = "L3"  # LLM review (Phase 2)
    L4 = "L4"  # Human-in-the-loop (Phase 2)


@dataclass
class ApprovalResult:
    approved: bool
    level: ApprovalLevel
    reason: str = ""
    details: str = ""