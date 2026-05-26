"""Skill Manager — coordinates skill loading, manifest generation."""

from pathlib import Path

from harness.skill.manifest import ManifestGenerator
from harness.skill.types import SkillManifest
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
        return self.manifest_gen.generate_text(user_skill_access, skill_names)

    def get_manifest(
        self, user_skill_access: str | None = None,
        skill_names: list[str] | None = None,
    ) -> SkillManifest:
        """Get full SkillManifest object. Pass user_skill_access / skill_names to filter."""
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