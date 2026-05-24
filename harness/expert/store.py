"""ExpertAgentStore — JSON file CRUD for API-managed expert agents."""

import json
import structlog
from datetime import datetime, timezone
from pathlib import Path

from harness.expert.types import AgentProfile

logger = structlog.get_logger()


class ExpertAgentStore:
    """JSON file store for CRUD-managed expert agents stored in data/agents/."""

    def __init__(self, project_root: Path | None = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent
        self._store_dir = project_root / "data" / "agents"
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[AgentProfile]:
        profiles = []
        for json_path in sorted(self._store_dir.glob("*.json")):
            profile = self._load_from_path(json_path)
            if profile:
                profiles.append(profile)
        return profiles

    def get(self, name: str) -> AgentProfile | None:
        path = self._path_for(name)
        if path.exists():
            return self._load_from_path(path)
        return None

    def save(self, profile: AgentProfile) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not profile.created_at:
            profile.created_at = now
        profile.updated_at = now
        profile.source = "api"

        path = self._path_for(profile.name)
        data = profile.model_dump()
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # Also save SOUL.md beside the profile if soul_file points to API-managed path
        soul_dir = self._store_dir / profile.name
        logger.info("expert_agent_saved", name=profile.name, path=str(path))

    def save_soul(self, name: str, soul_content: str) -> Path:
        """Save SOUL.md content for an API-managed agent."""
        soul_dir = self._store_dir / name
        soul_dir.mkdir(parents=True, exist_ok=True)
        soul_path = soul_dir / "SOUL.md"
        soul_path.write_text(soul_content, encoding="utf-8")
        return soul_path

    def load_soul(self, name: str) -> str:
        """Load SOUL.md content for an API-managed agent."""
        soul_path = self._store_dir / name / "SOUL.md"
        if soul_path.exists():
            return soul_path.read_text(encoding="utf-8")
        return ""

    def delete(self, name: str) -> bool:
        path = self._path_for(name)
        if not path.exists():
            return False
        path.unlink()
        # Remove soul directory
        soul_dir = self._store_dir / name
        if soul_dir.exists():
            import shutil
            shutil.rmtree(soul_dir)
        logger.info("expert_agent_deleted", name=name)
        return True

    def get_soul_path(self, name: str) -> str:
        """Return the relative soul file path for use in AgentProfile.soul_file."""
        soul_dir = self._store_dir / name
        return str(soul_dir / "SOUL.md")

    def _path_for(self, name: str) -> Path:
        return self._store_dir / f"{name}.json"

    @staticmethod
    def _load_from_path(path: Path) -> AgentProfile | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return AgentProfile(**data)
        except Exception as e:
            logger.warning("expert_agent_load_failed", path=str(path), error=str(e))
            return None
