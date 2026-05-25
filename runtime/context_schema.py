"""UserContext — RuntimeContext for multi-user isolation."""

from dataclasses import dataclass, field
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"

    @property
    def level(self) -> int:
        _order = {"admin": 3, "manager": 2, "operator": 1, "viewer": 0}
        return _order[self.value]

    def can_access(self, target_role: "UserRole") -> bool:
        """Check if this role can access resources of target_role level."""
        return self.level >= target_role.level


@dataclass
class UserContext:
    user_id: str
    tenant_id: str = "default"
    role: UserRole = UserRole.OPERATOR
    permissions: list[str] = field(default_factory=list)
    memory_path: str = ""
    session_id: str = ""
    preferences: dict = field(default_factory=dict)
    agent_id: str = ""  # Expert agent ID — empty for default agent

    def get_memory_path(self, base_dir: str) -> str:
        if not self.memory_path:
            if self.agent_id:
                self.memory_path = f"{base_dir}/users/{self.user_id}/agents/{self.agent_id}"
            else:
                self.memory_path = f"{base_dir}/users/{self.user_id}"
        return self.memory_path