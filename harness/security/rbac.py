"""RBAC module - loads role-based access control config from YAML."""

from pathlib import Path
from collections.abc import Sequence

import yaml

from harness.skill.types import SkillAccess
from runtime.context_schema import UserRole
from runtime.tools import BASE_TOOLS


DEFAULT_RBAC_CONFIG_PATH = "config/rbac.yaml"


def load_rbac_config(yaml_path: str | None = None) -> dict:
    """Load RBAC configuration from YAML file."""
    path = Path(yaml_path or DEFAULT_RBAC_CONFIG_PATH)
    if not path.exists():
        raise FileNotFoundError(f"RBAC config file not found: {path}")

    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_rbac_config(rbac_config: dict, yaml_path: str | None = None) -> None:
    """Save RBAC configuration to YAML and clear derived permission caches."""
    path = Path(yaml_path or DEFAULT_RBAC_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(rbac_config, f, sort_keys=False, allow_unicode=True)
    clear_rbac_caches()


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


_ROLE_TOOL_ACCESS_CACHE: dict | None = None
_ROLE_MCP_TOOL_ACCESS_CACHE: dict | None = None


def clear_rbac_caches() -> None:
    """Clear lazy-loaded role permission caches."""
    global _ROLE_TOOL_ACCESS_CACHE, _ROLE_MCP_TOOL_ACCESS_CACHE
    _ROLE_TOOL_ACCESS_CACHE = None
    _ROLE_MCP_TOOL_ACCESS_CACHE = None


def get_role_tool_access() -> dict[UserRole, list[str]]:
    """Get the ROLE_TOOL_ACCESS mapping (lazy-loaded from YAML)."""
    global _ROLE_TOOL_ACCESS_CACHE
    if _ROLE_TOOL_ACCESS_CACHE is None:
        config = load_rbac_config()
        _ROLE_TOOL_ACCESS_CACHE = build_role_tool_access(config)
    return _ROLE_TOOL_ACCESS_CACHE


def build_role_mcp_tool_access(rbac_config: dict) -> dict[UserRole, list[str]]:
    """Build the role -> MCP tool name mapping from RBAC YAML config."""
    role_map = {}
    roles_section = rbac_config.get("rbac", {}).get("roles", {})

    for role_name, role_data in roles_section.items():
        role_enum = UserRole(role_name)
        role_map[role_enum] = role_data.get("mcp_tools", [])

    for role in UserRole:
        if role not in role_map:
            role_map[role] = []

    return role_map


def get_role_mcp_tool_access() -> dict[UserRole, list[str]]:
    """Get the role -> MCP tool access mapping (lazy-loaded from YAML)."""
    global _ROLE_MCP_TOOL_ACCESS_CACHE
    if _ROLE_MCP_TOOL_ACCESS_CACHE is None:
        config = load_rbac_config()
        _ROLE_MCP_TOOL_ACCESS_CACHE = build_role_mcp_tool_access(config)
    return _ROLE_MCP_TOOL_ACCESS_CACHE


def get_role_skill_access(role: UserRole) -> str:
    """Get the skill_access level for a role from RBAC config (default: 'all')."""
    config = load_rbac_config()
    roles_section = config.get("rbac", {}).get("roles", {})
    role_data = roles_section.get(role.value, {})
    return role_data.get("skill_access", "all")


def normalize_roles(roles: Sequence[str | UserRole]) -> list[UserRole]:
    """Normalize role names/enums to unique UserRole values in input order."""
    normalized: list[UserRole] = []
    for role in roles:
        role_enum = role if isinstance(role, UserRole) else UserRole(role)
        if role_enum not in normalized:
            normalized.append(role_enum)
    return normalized


def _max_skill_level(role: UserRole, role_data: dict) -> int:
    skill_access = role_data.get("skill_access", "all")
    if isinstance(skill_access, SkillAccess):
        return skill_access.level
    if str(skill_access).lower() == SkillAccess.ALL.value:
        return SkillAccess.ALL.level
    return SkillAccess.max_for_role(str(skill_access))


def _role_allows_skill_from_data(role: UserRole, role_data: dict, skill) -> bool:
    if "skills" in role_data:
        allowed = role_data.get("skills") or []
        return "*" in allowed or skill.name in allowed

    return skill.access.level <= _max_skill_level(role, role_data)


def role_allows_skill(role: UserRole, skill) -> bool:
    """Return whether a role can access a skill under the RBAC config."""
    config = load_rbac_config()
    roles_section = config.get("rbac", {}).get("roles", {})
    role_data = roles_section.get(role.value, {})
    return _role_allows_skill_from_data(role, role_data, skill)


def _find_skill(skill_name: str, all_skills: list):
    for skill in all_skills:
        if skill.name == skill_name:
            return skill
    raise ValueError(f"Unknown skill: {skill_name}")


def roles_for_skill(skill_name: str, all_skills: list) -> list[UserRole]:
    """Return roles that can access the named skill."""
    skill = _find_skill(skill_name, all_skills)
    config = load_rbac_config()
    roles_section = config.get("rbac", {}).get("roles", {})
    roles: list[UserRole] = []

    for role in UserRole:
        role_data = roles_section.get(role.value, {})
        if _role_allows_skill_from_data(role, role_data, skill):
            roles.append(role)

    return roles


def _effective_skill_names(role: UserRole, role_data: dict, all_skills: list) -> list[str]:
    if "skills" in role_data:
        allowed = role_data.get("skills") or []
        if "*" not in allowed:
            return list(allowed)

        all_skill_names = [skill.name for skill in all_skills]
        explicit_names = [name for name in allowed if name != "*"]
        return list(dict.fromkeys([*all_skill_names, *explicit_names]))

    max_level = _max_skill_level(role, role_data)
    return [skill.name for skill in all_skills if skill.access.level <= max_level]


def set_skill_roles(
    skill_name: str,
    roles: Sequence[str | UserRole],
    all_skills: list,
) -> None:
    """Update the exact role allow-list for one skill and persist RBAC config."""
    _find_skill(skill_name, all_skills)
    selected_roles = set(normalize_roles(roles))
    config = load_rbac_config()
    roles_section = config.setdefault("rbac", {}).setdefault("roles", {})

    for role in UserRole:
        role_data = roles_section.setdefault(role.value, {})
        current_skills = _effective_skill_names(role, role_data, all_skills)
        next_skills = [
            name for name in current_skills if name not in {skill_name, "*"}
        ]
        if role in selected_roles:
            next_skills.append(skill_name)
        role_data["skills"] = sorted(dict.fromkeys(next_skills))

    save_rbac_config(config)


def roles_for_mcp_server(server_name: str) -> list[UserRole]:
    """Return roles with effective access to any tool from an MCP server."""
    config = load_rbac_config()
    roles_section = config.get("rbac", {}).get("roles", {})
    server_prefix = f"{server_name}:"
    roles: list[UserRole] = []

    for role in UserRole:
        entries = roles_section.get(role.value, {}).get("mcp_tools", []) or []
        if "*" in entries or any(entry.startswith(server_prefix) for entry in entries):
            roles.append(role)

    return roles


def set_mcp_server_roles(
    server_name: str,
    roles: Sequence[str | UserRole],
) -> None:
    """Replace role assignments for one MCP server and persist RBAC config."""
    selected_roles = set(normalize_roles(roles))
    config = load_rbac_config()
    roles_section = config.setdefault("rbac", {}).setdefault("roles", {})
    server_prefix = f"{server_name}:"
    server_wildcard = f"{server_name}:*"

    for role in UserRole:
        role_data = roles_section.setdefault(role.value, {})
        current_entries = role_data.get("mcp_tools", []) or []
        next_entries = [
            entry
            for entry in current_entries
            if entry != server_wildcard and not entry.startswith(server_prefix)
        ]
        if role in selected_roles:
            next_entries.append(server_wildcard)
        role_data["mcp_tools"] = list(dict.fromkeys(next_entries))

    save_rbac_config(config)
