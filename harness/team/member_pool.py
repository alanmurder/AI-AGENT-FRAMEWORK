"""TeamMemberPool — manages team member lifecycle and task claiming."""

import uuid
import yaml
import structlog
from pathlib import Path
from datetime import datetime

from harness.team.types import TaskItem, TeamMemberConfig, TaskStatus, TeamConfig
from harness.team.task_board import TaskBoardManager
from runtime.config import AgentConfig

logger = structlog.get_logger()


class TeamMemberPool:
    """Manages team member creation, task claiming, idle timeout, and shutdown."""

    def __init__(self, config: AgentConfig, board_mgr: TaskBoardManager | None = None):
        self.config = config
        self.task_board = board_mgr or TaskBoardManager(config)
        self.members: dict[str, TeamMemberConfig] = {}

    def spawn_member(self, role_prompt: str) -> str:
        """Create a new team member with a dynamic role prompt."""
        member_id = f"member-{uuid.uuid4().hex[:6]}"
        member = TeamMemberConfig(
            agent_id=member_id,
            role_prompt=role_prompt,
            status="idle",
            idle_timeout=self.config.member_idle_timeout,
            last_active_at=datetime.now().isoformat(),
        )
        self.members[member_id] = member
        logger.info("member_spawned", member_id=member_id)
        return member_id

    def claim_task_for_member(self, member_id: str, board_id: str = "team-default") -> TaskItem | None:
        """Find and claim a claimable task for a specific member."""
        member = self.members.get(member_id)
        if not member or member.status != "idle":
            return None

        tasks = self.task_board.list_tasks(board_id)
        for task in tasks:
            if task.status == TaskStatus.PENDING and self.task_board.can_claim(board_id, task.task_id):
                if self.task_board.claim_task(board_id, task.task_id, member_id):
                    member.status = "working"
                    member.last_active_at = datetime.now().isoformat()
                    logger.info("member_claimed_task", member_id=member_id, task_id=task.task_id)
                    return task
        return None

    def submit_result(self, board_id: str, task_id: str, result: str, member_id: str) -> None:
        """Submit task result and mark member as idle again."""
        self.task_board.submit_result(board_id, task_id, result)
        member = self.members.get(member_id)
        if member:
            member.status = "idle"
            member.last_active_at = datetime.now().isoformat()

    def check_idle_members(self) -> list[str]:
        """Check for members that have exceeded their idle timeout."""
        now = datetime.now()
        idle_ids = []
        for member_id, member in self.members.items():
            if member.status == "idle":
                last_active = datetime.fromisoformat(member.last_active_at) if member.last_active_at else now
                elapsed = (now - last_active).total_seconds()
                if elapsed >= member.idle_timeout:
                    idle_ids.append(member_id)
        return idle_ids

    def shutdown_member(self, member_id: str) -> None:
        """Remove a member from the pool."""
        member = self.members.pop(member_id, None)
        if member:
            logger.info("member_shutdown", member_id=member_id)


class TeamManager:
    """Scans and manages TeamConfig definitions."""

    def __init__(self, config: AgentConfig):
        self.config = config

    def scan_teams(self, root: Path) -> list[TeamConfig]:
        """Scan agents/teams/ directory for team YAML files."""
        teams_dir = root / "agents" / "teams"
        if not teams_dir.exists():
            return []

        teams = []
        for team_yaml in teams_dir.glob("*.yaml"):
            team = self._parse_team_yaml(team_yaml)
            if team:
                teams.append(team)
        return teams

    def _parse_team_yaml(self, path: Path) -> TeamConfig | None:
        """Parse a team YAML file into TeamConfig."""
        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            return TeamConfig(**data)
        except Exception as e:
            logger.warning("team_parse_failed", path=str(path), error=str(e))
            return None