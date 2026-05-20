"""RBAC module — loads role-based access control config from YAML."""

import yaml
from pathlib import Path
from typing import Optional

from runtime.context_schema import UserContext, UserRole
from runtime.tools import BASE_TOOLS


def load_rbac_config(yaml_path: str = "config/rbac.yaml") -> dict:
    """Load RBAC configuration from YAML file."""
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"RBAC config file not found: {yaml_path}")

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_role_tool_access(rbac_config: dict) -> dict[UserRole, list[str]]:
    """Build the ROLE_TOOL_ACCESS mapping from RBAC YAML config."""
    role_map = {}
    roles_section = rbac_config.get("rbac", {}).get("roles", {})

    for role_name, role_data in roles_section.items():
        role_enum = UserRole(role_name)
        role_map[role_enum] = role_data.get("tools", [])

    # Ensure all defined roles have entries
    for role in UserRole:
        if role not in role_map:
            role_map[role] = [t.name for t in BASE_TOOLS] if role == UserRole.ADMIN else []

    return role_map


# Lazy-loaded singleton cache
_ROLE_TOOL_ACCESS_CACHE: dict | None = None


def get_role_tool_access() -> dict[UserRole, list[str]]:
    """Get the ROLE_TOOL_ACCESS mapping (lazy-loaded from YAML)."""
    global _ROLE_TOOL_ACCESS_CACHE
    if _ROLE_TOOL_ACCESS_CACHE is None:
        config = load_rbac_config()
        _ROLE_TOOL_ACCESS_CACHE = build_role_tool_access(config)
    return _ROLE_TOOL_ACCESS_CACHE


def get_role_skill_access(role: UserRole) -> str:
    """Get the skill_access level for a role from RBAC config (default: 'all')."""
    config = load_rbac_config()
    roles_section = config.get("rbac", {}).get("roles", {})
    role_data = roles_section.get(role.value, {})
    return role_data.get("skill_access", "all")