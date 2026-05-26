"""Skill Manager — coordinates skill loading, manifest generation."""

from pathlib import Path

from harness.security.rbac import role_allows_skill
from harness.skill.manifest import ManifestGenerator
from harness.skill.types import SkillManifest
from runtime.context_schema import UserRole
from runtime.config import AgentConfig


class SkillManager:
    """Manages skill discovery, manifest generation, and SKILL.md loading."""

    def __init__(self, config: AgentConfig, project_root: Path | None = None):
        # Use explicit project_root parameter if provided, otherwise fall back to config
        if project_root is not None:
            root = project_root
        elif config.project_root:
            root = Path(config.project_root)
        else:
            # Last resort: derive from this file's location (fragile but backwards-compatible)
            root = Path(__file__).parent.parent.parent

        self.manifest_gen = ManifestGenerator(
            builtin_dir=root / "skills" / "builtin",
            extension_dir=root / "skills" / "extensions",
        )

    def generate_manifest(
        self, user_skill_access: str | None = None,
        skill_names: list[str] | None = None,
    ) -> str:
        """Generate skill manifest text for prompt injection (~200 tokens).

        user_skill_access: optional role skill_access value for filtering
        (e.g. 'admin', 'manager', 'operator', 'viewer').
        skill_names: if provided (non-None), further filter to only these skill names.
        """
        return self.get_manifest(user_skill_access, skill_names).to_text()

    def get_manifest(
        self, user_skill_access: str | None = None,
        skill_names: list[str] | None = None,
    ) -> SkillManifest:
        """Get full SkillManifest object. Pass user_skill_access / skill_names to filter."""
        role = self._as_user_role(user_skill_access)
        if role is not None:
            skills = self.list_skills_for_role(role)
            if skill_names is not None:
                name_set = set(skill_names)
                skills = [skill for skill in skills if skill.name in name_set]
            return SkillManifest(skills=skills)
        return self.manifest_gen.generate(user_skill_access, skill_names)

    def load_skill_content(self, skill_name: str) -> str | None:
        """Load full SKILL.md content for a specific skill (for on-demand reading)."""
        manifest = self.get_manifest()
        for skill in manifest.skills:
            if skill.name == skill_name:
                path = Path(skill.location)
                if path.exists():
                    return path.read_text(encoding="utf-8")
        return None

    def list_skills(self) -> list:
        """List all skills as SkillInfo objects (with access levels)."""
        manifest = self.get_manifest()
        return manifest.skills

    def get_skill(self, skill_name: str):
        """Return a SkillInfo by name, or None when not found."""
        for skill in self.get_manifest().skills:
            if skill.name == skill_name:
                return skill
        return None

    def list_skills_for_role(self, role) -> list:
        """List skills the role can access under the RBAC config."""
        role_enum = role if isinstance(role, UserRole) else UserRole(role)
        return [
            skill
            for skill in self.list_skills()
            if role_allows_skill(role_enum, skill)
        ]

    @staticmethod
    def _as_user_role(value) -> UserRole | None:
        if value is None:
            return None
        try:
            return value if isinstance(value, UserRole) else UserRole(value)
        except ValueError:
            return None
