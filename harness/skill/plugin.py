"""Plugin Manager — groups Skills into Plugins for progressive disclosure."""

import structlog
from pathlib import Path
from pydantic import BaseModel

from harness.skill.manager import SkillManager

logger = structlog.get_logger()


class PluginInfo(BaseModel):
    name: str
    description: str
    skills: list[str] = []
    location: str = ""


class PluginManager:
    """Manages plugin discovery, manifest generation, and skill grouping."""

    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager

    def scan_plugins(self, root: Path) -> list[PluginInfo]:
        """Scan skills/plugins/ directory for PLUGIN.md files."""
        plugins = []
        plugins_dir = root / "skills" / "plugins"
        if not plugins_dir.exists():
            return plugins

        for plugin_md in plugins_dir.rglob("PLUGIN.md"):
            plugin_dir = plugin_md.parent
            info = self._parse_plugin_md(plugin_md, plugin_dir)
            if info:
                plugins.append(info)

        return plugins

    def generate_plugin_manifest(self, root: Path) -> str:
        """Generate Plugin manifest text for prompt injection (~100 tokens per plugin).

        Only generated if plugin count > 3, otherwise individual Skills are sufficient.
        """
        plugins = self.scan_plugins(root)
        if len(plugins) <= 3:
            return ""

        lines = ["Available Plugins:"]
        for plugin in plugins:
            skill_names = ", ".join(plugin.skills) if plugin.skills else "(no skills)"
            lines.append(f"- {plugin.name}: {plugin.description} [{skill_names}]")
        return "\n".join(lines)

    def load_plugin(self, plugin_name: str, root: Path) -> PluginInfo | None:
        """Load a specific Plugin's details."""
        plugins = self.scan_plugins(root)
        for plugin in plugins:
            if plugin.name == plugin_name:
                return plugin
        return None

    def create_plugin(self, name: str, description: str, skills: list[str], root: Path) -> PluginInfo:
        """Create a new Plugin directory with PLUGIN.md."""
        plugin_dir = root / "skills" / "plugins" / name
        plugin_dir.mkdir(parents=True, exist_ok=True)

        plugin_md = plugin_dir / "PLUGIN.md"
        skill_list = "\n  - ".join(skills) if skills else "  - (none)"
        content = f"""---
name: {name}
description: {description}
---

# Plugin: {name}

{description}

## Skills
{skill_list}
"""
        plugin_md.write_text(content, encoding="utf-8")

        return PluginInfo(
            name=name,
            description=description,
            skills=skills,
            location=str(plugin_dir),
        )

    def _parse_plugin_md(self, plugin_md: Path, plugin_dir: Path) -> PluginInfo | None:
        """Parse PLUGIN.md frontmatter to extract PluginInfo."""
        try:
            content = plugin_md.read_text(encoding="utf-8")
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

            # Parse skills list from body
            skills = []
            body = parts[2].strip()
            in_skills_section = False
            for line in body.split("\n"):
                line_stripped = line.strip()
                if "## Skills" in line:
                    in_skills_section = True
                    continue
                if in_skills_section and line_stripped.startswith("##"):
                    break
                if in_skills_section and line_stripped.startswith("-"):
                    skill_name = line_stripped.lstrip("- ").strip()
                    if skill_name and skill_name != "(none)":
                        skills.append(skill_name)

            # Also scan for actual SKILL.md files in subdirectory
            skills_dir = plugin_dir / "skills"
            if skills_dir.exists():
                for skill_md in skills_dir.rglob("SKILL.md"):
                    # Try to parse skill name from frontmatter
                    try:
                        skill_content = skill_md.read_text(encoding="utf-8")
                        if skill_content.startswith("---"):
                            skill_parts = skill_content.split("---", 2)
                            for sl in skill_parts[1].strip().split("\n"):
                                if sl.startswith("name:"):
                                    skills.append(sl.split(":", 1)[1].strip())
                    except Exception:
                        pass

            return PluginInfo(
                name=metadata.get("name", plugin_dir.name),
                description=metadata.get("description", ""),
                skills=skills,
                location=str(plugin_dir),
            )
        except Exception:
            return None