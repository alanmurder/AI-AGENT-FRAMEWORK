"""Cron scheduler — user-configured scheduled tasks with 5-field cron expressions."""

import uuid
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from harness.scheduler.types import CronTask, HeartbeatResult, TaskStatus, TaskType
from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole


class CronScheduler:
    """Manages user-defined cron tasks using APScheduler.

    Each cron task is a scheduled prompt that runs against an independent
    agent session at the specified cron interval.
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self._scheduler = BackgroundScheduler()
        self._tasks: dict[str, CronTask] = {}
        self._callbacks: dict[str, callable] = {}  # task_id -> callback

    def add_task(self, task: CronTask) -> None:
        """Add and schedule a cron task."""
        self._tasks[task.task_id] = task
        self._callbacks[task.task_id] = None  # will be set via register_callback
        self._scheduler.add_job(
            self._execute_task,
            "cron",
            **self._parse_cron_expression(task.cron_expression),
            id=task.task_id,
            name=task.name,
            args=[task.task_id],
        )
        task.status = TaskStatus.PENDING

    def remove_task(self, task_id: str) -> bool:
        """Remove a cron task by ID."""
        if task_id not in self._tasks:
            return False
        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass  # Job may not exist if scheduler hasn't started
        del self._tasks[task_id]
        self._callbacks.pop(task_id, None)
        return True

    def register_callback(self, task_id: str, callback: callable) -> None:
        """Register a callback to be invoked when the task completes."""
        self._callbacks[task_id] = callback

    def list_tasks(self, user_id: str = None) -> list[CronTask]:
        """List all tasks, optionally filtered by user_id."""
        if user_id:
            return [t for t in self._tasks.values() if t.user_id == user_id]
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> CronTask | None:
        """Get a specific task by ID."""
        return self._tasks.get(task_id)

    def start(self) -> None:
        """Start the cron scheduler."""
        self._scheduler.start()

    def stop(self) -> None:
        """Stop the cron scheduler."""
        self._scheduler.shutdown(wait=False)

    def _parse_cron_expression(self, expr: str) -> dict:
        """Parse a 5-field cron expression into APScheduler kwargs.

        Format: minute hour day-of-month month day-of-week
        Maps to APScheduler's: minute, hour, day, month, day_of_week
        """
        fields = expr.strip().split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression: '{expr}'. Expected 5 fields: minute hour day month day_of_week")

        return {
            "minute": fields[0],
            "hour": fields[1],
            "day": fields[2],
            "month": fields[3],
            "day_of_week": fields[4],
        }

    def _execute_task(self, task_id: str) -> None:
        """Execute a scheduled cron task."""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = TaskStatus.RUNNING
        try:
            result = self._run_agent(task)
            task.status = TaskStatus.COMPLETED

            callback = self._callbacks.get(task_id)
            if callback:
                callback(result)
        except Exception as e:
            task.status = TaskStatus.FAILED

    def _run_agent(self, task: CronTask) -> HeartbeatResult:
        """Create an independent agent session and run the cron prompt."""
        session_id = f"cron-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        user_ctx = UserContext(
            user_id=task.user_id,
            role=UserRole.OPERATOR,
            tenant_id="default",
            permissions=[],
            memory_path="",
            session_id=session_id,
        )

        # Import here to avoid circular imports
        from runtime.agent import create_agent_for_user
        from harness.memory.manager import MemoryManager
        from harness.skill.manager import SkillManager
        from harness.security.approval import ApprovalChecker
        from harness.sandbox.manager import SandboxManager
        from runtime.models import create_mini_model
        from pathlib import Path

        mini = create_mini_model(self.config)
        mm = MemoryManager(self.config, mini_model=mini)
        root = Path(self.config.project_root) if self.config.project_root else Path(__file__).parent.parent.parent
        sm = SkillManager(self.config, project_root=root)
        ac = ApprovalChecker(mini_model=mini)

        mm.init_user(task.user_id)

        agent = create_agent_for_user(user_ctx, self.config, mm, sm, ac, sandbox_runner=SandboxManager.from_config(self.config))

        result = agent.invoke(
            {"messages": [{"role": "user", "content": task.prompt}]},
            config={"configurable": {"context": user_ctx}},
        )

        # Extract AI response content
        ai_content = ""
        for msg in result.get("messages", []):
            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                ai_content = msg.content

        return HeartbeatResult(
            user_id=task.user_id,
            timestamp=datetime.now().isoformat(),
            summary=ai_content[:500],
            anomalies=[],
            actions_taken=[f"cron_task:{task.task_id}"],
        )


def create_cron_task(
    name: str,
    cron_expression: str,
    user_id: str,
    prompt: str,
    channel: str = "web",
) -> CronTask:
    """Factory function to create a CronTask with a generated ID."""
    task_id = f"cron-{uuid.uuid4().hex[:8]}"
    return CronTask(
        task_id=task_id,
        name=name,
        cron_expression=cron_expression,
        user_id=user_id,
        prompt=prompt,
        channel=channel,
    )
