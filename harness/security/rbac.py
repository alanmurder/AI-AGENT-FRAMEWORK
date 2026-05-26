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
        denied = [f"!{entry}" for entry in role_data.get("mcp_tools_denied", []) or []]
        role_map[role_enum] = [
            *(role_data.get("mcp_tools", []) or []),
            *denied,
        ]

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


def _mcp_pattern_matches(full_name: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    if pattern == full_name:
        return True
    if pattern.endswith(":*"):
        prefix = pattern[:-2]
        return full_name.startswith(prefix + ":")
    return False


def mcp_tool_allowed(full_name: str, allowed: Sequence[str]) -> bool:
    """Return whether an MCP server:tool name is allowed, honoring ! deny patterns."""
    for pattern in allowed:
        if isinstance(pattern, str) and pattern.startswith("!"):
            if _mcp_pattern_matches(full_name, pattern[1:]):
                return False

    return any(_mcp_pattern_matches(full_name, pattern) for pattern in allowed)


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
    denied = role_data.get("skills_denied") or []
    if "*" in denied or skill.name in denied:
        return False

    allowed_overrides = role_data.get("skills_allowed") or []
    if "*" in allowed_overrides or skill.name in allowed_overrides:
        return True

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
    skill = _find_skill(skill_name, all_skills)
    selected_roles = set(normalize_roles(roles))
    config = load_rbac_config()
    roles_section = config.setdefault("rbac", {}).setdefault("roles", {})

    for role in UserRole:
        role_data = roles_section.setdefault(role.value, {})
        has_exact_skills = "skills" in role_data
        current_skills = list(role_data.get("skills") or [])
        current_allowed = [
            name for name in role_data.get("skills_allowed", []) if name != skill_name
        ]
        current_denied = [
            name for name in role_data.get("skills_denied", []) if name != skill_name
        ]

        if role in selected_roles:
            if has_exact_skills:
                if "*" not in current_skills and skill_name not in current_skills:
                    current_skills.append(skill_name)
            elif skill.access.level > _max_skill_level(role, role_data):
                current_allowed.append(skill_name)
        elif has_exact_skills:
            if "*" in current_skills:
                current_denied.append(skill_name)
            else:
                current_skills = [name for name in current_skills if name != skill_name]
        elif skill.access.level <= _max_skill_level(role, role_data):
            current_denied.append(skill_name)

        if has_exact_skills:
            role_data["skills"] = sorted(dict.fromkeys(current_skills))
        if current_allowed:
            role_data["skills_allowed"] = sorted(dict.fromkeys(current_allowed))
        else:
            role_data.pop("skills_allowed", None)
        if current_denied:
            role_data["skills_denied"] = sorted(dict.fromkeys(current_denied))
        else:
            role_data.pop("skills_denied", None)

    save_rbac_config(config)


def roles_for_mcp_server(server_name: str) -> list[UserRole]:
    """Return roles with effective access to any tool from an MCP server."""
    config = load_rbac_config()
    roles_section = config.get("rbac", {}).get("roles", {})
    server_prefix = f"{server_name}:"
    server_wildcard = f"{server_name}:*"
    roles: list[UserRole] = []

    for role in UserRole:
        role_data = roles_section.get(role.value, {})
        entries = role_data.get("mcp_tools", []) or []
        denied = role_data.get("mcp_tools_denied", []) or []
        if "*" in denied or server_wildcard in denied:
            continue
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
        current_denied = [
            entry for entry in role_data.get("mcp_tools_denied", []) or []
            if entry != server_wildcard and not entry.startswith(server_prefix)
        ]
        next_entries = [
            entry
            for entry in current_entries
            if entry != server_wildcard and not entry.startswith(server_prefix)
        ]
        if role in selected_roles:
            if "*" not in current_entries:
                next_entries.append(server_wildcard)
        elif "*" in current_entries:
            current_denied.append(server_wildcard)
        role_data["mcp_tools"] = list(dict.fromkeys(next_entries))
        if current_denied:
            role_data["mcp_tools_denied"] = list(dict.fromkeys(current_denied))
        else:
            role_data.pop("mcp_tools_denied", None)

    save_rbac_config(config)
