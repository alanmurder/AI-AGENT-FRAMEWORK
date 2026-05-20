"""AgentRegistry — scans, registers, and manages expert AgentProfiles."""

import yaml
import structlog
from pathlib import Path

from harness.expert.types import AgentProfile

logger = structlog.get_logger()


class AgentRegistry:
    """In-memory registry of AgentProfiles."""

    def __init__(self):
        self._profiles: dict[str, AgentProfile] = {}

    def scan_profiles(self, agents_dir: Path) -> list[AgentProfile]:
        """Scan agents/ directory for profile.yaml files."""
        if not agents_dir.exists():
            return []

        profiles = []
        for profile_yaml in agents_dir.rglob("profile.yaml"):
            # Skip profiles inside teams directory
            if "teams" in profile_yaml.parts:
                continue
            profile = self._parse_profile_yaml(profile_yaml)
            if profile:
                self._profiles[profile.name] = profile
                profiles.append(profile)

        logger.info("registry_scanned", count=len(profiles))
        return profiles

    def register(self, profile: AgentProfile) -> str:
        """Register an AgentProfile dynamically."""
        self._profiles[profile.name] = profile
        logger.info("registry_registered", name=profile.name)
        return profile.name

    def get(self, name: str) -> AgentProfile | None:
        """Get a profile by name."""
        return self._profiles.get(name)

    def list_profiles(self) -> list[AgentProfile]:
        """List all registered profiles."""
        return list(self._profiles.values())

    def generate_manifest(self) -> str:
        """Generate manifest text for agent marketplace display."""
        if not self._profiles:
            return ""
        lines = ["Available Expert Agents:"]
        for p in self._profiles.values():
            lines.append(f"- {p.name} ({p.display_name}): {p.description}")
        return "\n".join(lines)

    def load_soul_content(self, name: str, root: Path) -> str:
        """Load SOUL.md content for a specific expert."""
        profile = self._profiles.get(name)
        if not profile:
            return ""
        soul_path = root / profile.soul_file
        if soul_path.exists():
            return soul_path.read_text(encoding="utf-8")
        return ""

    def _parse_profile_yaml(self, path: Path) -> AgentProfile | None:
        """Parse a profile.yaml file into AgentProfile."""
        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            return AgentProfile(**data)
        except Exception as e:
            logger.warning("profile_parse_failed", path=str(path), error=str(e))
            return None