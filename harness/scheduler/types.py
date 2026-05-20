"""Scheduler type definitions."""

from dataclasses import dataclass, field
from enum import Enum


class TaskType(str, Enum):
    HEARTBEAT = "heartbeat"
    CRON = "cron"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CronTask:
    task_id: str
    name: str
    cron_expression: str
    user_id: str
    prompt: str
    channel: str = "web"
    status: TaskStatus = TaskStatus.PENDING


@dataclass
class HeartbeatResult:
    user_id: str
    timestamp: str
    summary: str = ""
    anomalies: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)