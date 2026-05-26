"""Heartbeat scheduler — periodic agent health-check, proactive monitoring, and memory extraction."""

import asyncio
import uuid
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from harness.scheduler.types import HeartbeatResult, TaskType
from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole


HEARTBEAT_PROMPT = (
    "You are performing a routine heartbeat check. Review your task list, "
    "memory, and any pending items. Check for anomalies in production data "
    "or recent activity. Provide a brief summary of the current state, "
    "any anomalies detected, and recommended actions. "
    "If everything is normal, just say 'All systems normal.'"
)


class HeartbeatScheduler:
    """Triggers periodic agent wake-ups and memory extraction tasks.

    Every heartbeat cycle:
    - Agent wake-up: evaluates state, checks anomalies (per registered user)
    - Memory heartbeat: batch-extracts cross-session facts/prefs from PG summaries
    """

    def __init__(self, config: AgentConfig, interval_minutes: int = 30):
        self.config = config
        self.interval_minutes = interval_minutes
        self._scheduler = BackgroundScheduler()
        self._user_callbacks: dict[str, callable] = {}
        self._async_tasks: list = []  # (task, name) tuples

    def register_user(self, user_id: str, callback: callable) -> None:
        """Register a callback to be invoked when heartbeat completes for a user."""
        self._user_callbacks[user_id] = callback

    def register_async_task(self, task, name: str) -> None:
        """Register an async callable to run on each heartbeat cycle."""
        self._async_tasks.append((task, name))

    def start(self) -> None:
        """Start the heartbeat scheduler."""
        self._scheduler.add_job(
            self._run_heartbeat,
            "interval",
            minutes=self.interval_minutes,
            id="heartbeat",
            name="Agent Heartbeat",
        )
        self._scheduler.start()

    def stop(self) -> None:
        """Stop the heartbeat scheduler."""
        self._scheduler.shutdown(wait=False)

    def _run_heartbeat(self) -> None:
        """Execute heartbeat for all registered users + async memory tasks."""
        for user_id, callback in self._user_callbacks.items():
            try:
                result = self.execute_heartbeat(user_id)
                if callback:
                    callback(result)
            except Exception:
                pass

        # Run registered async tasks (e.g. MemoryHeartbeatTask)
        for task, name in self._async_tasks:
            try:
                asyncio.new_event_loop().run_until_complete(task.run())
            except Exception:
                import structlog
                structlog.get_logger().warning("heartbeat_async_task_failed", name=name)

    def execute_heartbeat(self, user_id: str) -> HeartbeatResult:
        """Execute a single heartbeat check for a user.

        Creates an independent agent session, runs the heartbeat prompt,
        and returns the result.
        """
        session_id = f"heartbeat-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        user_ctx = UserContext(
            user_id=user_id,
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

        mm.init_user(user_id)

        agent = create_agent_for_user(user_ctx, self.config, mm, sm, ac, sandbox_runner=SandboxManager.from_config(self.config))

        result = agent.invoke(
            {"messages": [{"role": "user", "content": HEARTBEAT_PROMPT}]},
            config={"configurable": {"context": user_ctx}},
        )

        # Extract response
        ai_content = ""
        for msg in result.get("messages", []):
            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                ai_content = msg.content

        return HeartbeatResult(
            user_id=user_id,
            timestamp=datetime.now().isoformat(),
            summary=ai_content[:500],
            anomalies=[],
            actions_taken=[],
        )
