"""Skill system type definitions."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class SkillCategory(str, Enum):
    FILE_MANAGER = "file_manager"
    KNOWLEDGE_SEARCH = "knowledge_search"
    REPORT_GENERATOR = "report_generator"
    SCHEDULE_MANAGER = "schedule_manager"
    NOTIFICATION = "notification"
    DATABASE_QUERY = "database_query"
    DATA_ANALYSIS = "data_analysis"


class SkillAccess(str, Enum):
    """Skill access level — lower level = wider visibility.

    Visibility hierarchy: report(0) → production(1) → enterprise(2) → all(3)
    A role with skill_access=X can see skills with access level ≤ X.
    """
    REPORT = "report"           # 0 — all roles
    PRODUCTION = "production"   # 1 — operator+
    ENTERPRISE = "enterprise"   # 2 — manager+
    ALL = "all"                 # 3 — admin only

    @property
    def level(self) -> int:
        _order = {self.REPORT: 0, self.PRODUCTION: 1, self.ENTERPRISE: 2, self.ALL: 3}
        return _order[self]

    @classmethod
    def max_for_role(cls, role_skill_access: str) -> int:
        """Return the maximum access level value visible to a role."""
        _role_max = {
            "admin": 3,
            "manager": 2,
            "enterprise": 2,
            "operator": 1,
            "production": 1,
            "viewer": 0,
            "report": 0,
        }
        return _role_max.get(role_skill_access.lower(), 0)


@dataclass
class SkillInfo:
    name: str
    description: str
    category: SkillCategory
    access: SkillAccess
    location: str
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    runtime: str = "host"           # "host" | "sandbox" | "docker"
    dependencies: list[str] = field(default_factory=list)
    timeout: int = 30
    network_access: bool = False
    max_memory: str = "256m"


@dataclass
class SkillManifest:
    skills: list[SkillInfo]

    def to_text(self) -> str:
        """Generate manifest text for prompt injection (~200 tokens)."""
        lines = ["Available Skills:"]
        for skill in self.skills:
            lines.append(f"- {skill.name} ({skill.description}) → {skill.location}")
        return "\n".join(lines)