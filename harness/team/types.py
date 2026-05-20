"""Agent Teams type definitions."""

from enum import Enum
from pydantic import BaseModel


class TaskStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskItem(BaseModel):
    task_id: str
    parent_task_id: str | None = None
    description: str
    role_prompt: str
    context: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assignee: str | None = None
    result: str = ""
    dependencies: list[str] = []
    created_at: str = ""
    completed_at: str = ""


class TaskBoard(BaseModel):
    board_id: str
    tasks: dict[str, TaskItem] = {}


class TeamMemberConfig(BaseModel):
    agent_id: str
    role_prompt: str
    status: str = "idle"
    idle_timeout: int = 300
    last_active_at: str = ""
    max_concurrent_tasks: int = 1


class TeamConfig(BaseModel):
    name: str
    display_name: str = ""
    captain: str = "default"
    members: list[str] = []
    description: str = ""