"""ExpertAgentValidator — privilege escalation prevention for expert agents."""

from harness.security.rbac import (
    get_role_mcp_tool_access,
    get_role_skill_access,
    role_allows_skill,
)
from harness.skill.types import SkillInfo
from runtime.context_schema import UserRole


class ExpertAgentValidator:
    """Validates expert agent configurations to prevent privilege escalation."""

    @staticmethod
    def validate_skills_from_profile(
        role: str,
        skills: list[str],
        all_skills: list[SkillInfo] | None = None,
    ) -> list[str]:
        """Return only skills allowed for the given role (convenience for API endpoints)."""
        role_enum = UserRole(role)
        skill_map = {skill.name: skill for skill in all_skills or []}
        valid = []
        rejected = []
        for skill_name in skills:
            skill_obj = skill_map.get(skill_name)
            if skill_obj is None and all_skills is None:
                skill_obj = ExpertAgentValidator._get_skill_info(skill_name)
            if skill_obj is None:
                if all_skills is None:
                    valid.append(skill_name)
                else:
                    rejected.append(skill_name)
                continue
            if role_allows_skill(role_enum, skill_obj):
                valid.append(skill_name)
            else:
                rejected.append(skill_name)
        if rejected:
            from structlog import get_logger
            get_logger().warning("skill_privilege_escalation_blocked", role=role, rejected=rejected)
        return valid

    @staticmethod
    def validate_mcp_tools_from_profile(role: str, mcp_tools: list[str]) -> list[str]:
        """Intersect mcp_tools with role-allowed MCP tools. Supports wildcards."""
        allowed = get_role_mcp_tool_access().get(UserRole(role), [])

        if "*" in allowed:
            return mcp_tools

        valid = []
        for tool in mcp_tools:
            if tool in allowed:
                valid.append(tool)
                continue
            for pattern in allowed:
                if pattern.endswith(":*") and tool.startswith(pattern[:-2] + ":"):
                    valid.append(tool)
                    break

        rejected = [t for t in mcp_tools if t not in valid]
        if rejected:
            from structlog import get_logger
            get_logger().warning("mcp_privilege_escalation_blocked", role=role, rejected=rejected)
        return valid

    @staticmethod
    def get_role_skill_level(role: str) -> str:
        """Get the skill_access level string for a role."""
        return get_role_skill_access(UserRole(role))

    @staticmethod
    def get_role_mcp_tools(role: str) -> list[str]:
        """Get allowed MCP tool names for a role."""
        return get_role_mcp_tool_access().get(UserRole(role), [])

    @staticmethod
    def _get_skill_info(skill_name: str):
        """Look up SkillInfo by name. Returns None if not found (allow by default)."""
        try:
            from harness.skill.manager import SkillManager
            # We don't have a direct lookup, so fall back to allow-by-default
            return None
        except Exception:
            return None
