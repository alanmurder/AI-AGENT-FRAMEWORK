"""Skill manifest generator — scans skill directories and produces injectable manifest."""

from pathlib import Path
from typing import Optional
from harness.skill.types import SkillInfo, SkillManifest, SkillCategory, SkillAccess


def parse_skill_md(path: Path) -> SkillInfo | None:
    """Parse SKILL.md frontmatter to extract SkillInfo."""
    try:
        content = path.read_text(encoding="utf-8")
        # Parse YAML-like frontmatter between --- markers
        if not content.startswith("---"):
            return None
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        metadata = {}
        for line in parts[1].strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()

        # Extract description from body (first non-heading paragraph)
        body = parts[2].strip()
        description = ""
        for line in body.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                description = line
                break

        # Parse list fields
        tags = metadata.get("tags", "").split(",") if metadata.get("tags") else []
        deps = metadata.get("dependencies", "").split(",") if metadata.get("dependencies") else []

        return SkillInfo(
            name=metadata.get("name", path.parent.name),
            description=description or metadata.get("description", ""),
            category=SkillCategory(metadata.get("category", "file_manager")),
            access=SkillAccess(metadata.get("access", "all")),
            location=str(path),
            version=metadata.get("version", "1.0.0"),
            tags=tags,
            runtime=metadata.get("runtime", "host"),
            dependencies=deps,
            timeout=int(metadata.get("timeout", "30")),
            network_access=metadata.get("network", "no").lower() in ("yes", "true", "1"),
            max_memory=metadata.get("max_memory", "256m"),
        )
    except Exception:
        return None


def scan_skills(base_dir: Path) -> list[SkillInfo]:
    """Scan a directory tree for SKILL.md files."""
    skills = []
    if not base_dir.exists():
        return skills

    for skill_md in base_dir.rglob("SKILL.md"):
        # Skip skills inside plugins directory (Phase 3+)
        if "plugins" in skill_md.parts:
            continue
        info = parse_skill_md(skill_md)
        if info:
            skills.append(info)
    return skills


class ManifestGenerator:
    """Generates SkillManifest from builtin and extension directories."""

    def __init__(self, builtin_dir: Path, extension_dir: Path):
        self.builtin_dir = builtin_dir
        self.extension_dir = extension_dir

    def generate(
        self, user_skill_access: str | None = None,
        skill_names: list[str] | None = None,
    ) -> SkillManifest:
        """Scan all skill directories and produce manifest.

        user_skill_access: role key for access-level filtering (e.g. 'admin', 'operator').
        skill_names: if provided (non-None), further filter to only these skill names.
                     Empty list → no skills. None → all role-allowed skills.
        """
        all_skills = []
        all_skills.extend(scan_skills(self.builtin_dir))
        all_skills.extend(scan_skills(self.extension_dir))

        if user_skill_access:
            max_level = SkillAccess.max_for_role(user_skill_access)
            all_skills = [s for s in all_skills if s.access.level <= max_level]

        if skill_names is not None:
            name_set = set(skill_names)
            all_skills = [s for s in all_skills if s.name in name_set]

        return SkillManifest(skills=all_skills)

    def generate_text(
        self, user_skill_access: str | None = None,
        skill_names: list[str] | None = None,
    ) -> str:
        """Generate manifest text for prompt injection."""
        return self.generate(user_skill_access, skill_names).to_text()