"""Background task manager — async queue + worker for non-blocking agent tasks."""

import uuid
import asyncio
import structlog
from datetime import datetime

from pydantic import BaseModel

from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole
from runtime.agent import create_agent_for_user
from harness.memory.manager import MemoryManager
from harness.skill.manager import SkillManager
from harness.security.approval import ApprovalChecker
from harness.sandbox.manager import SandboxManager

logger = structlog.get_logger()


class BackgroundTaskStatus(str):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundTask(BaseModel):
    task_id: str
    name: str
    user_id: str
    prompt: str
    status: str = BackgroundTaskStatus.PENDING
    created_at: str = ""
    completed_at: str = ""
    result: str = ""
    error: str | None = None


class BackgroundTaskManager:
    """Async background task manager — submit tasks, worker executes them."""

    def __init__(
        self,
        config: AgentConfig,
        memory_manager: MemoryManager,
        skill_manager: SkillManager,
        approval_checker: ApprovalChecker,
        sandbox_runner: SandboxManager | None = None,
    ):
        self.config = config
        self.memory_manager = memory_manager
        self.skill_manager = skill_manager
        self.approval_checker = approval_checker
        self.sandbox_runner = sandbox_runner
        self._tasks: dict[str, BackgroundTask] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._max_concurrent = config.background_max_concurrent if hasattr(config, "background_max_concurrent") else 3

    async def submit(self, name: str, prompt: str, user_id: str) -> str:
        """Submit a background task, returns task_id."""
        task_id = f"bg-{uuid.uuid4().hex[:8]}"
        task = BackgroundTask(
            task_id=task_id,
            name=name,
            user_id=user_id,
            prompt=prompt,
            created_at=datetime.now().isoformat(),
        )
        self._tasks[task_id] = task
        await self._queue.put(task_id)
        logger.info("background_task_submitted", task_id=task_id, name=name, user_id=user_id)
        return task_id

    async def get_status(self, task_id: str) -> BackgroundTask | None:
        """Query task status by task_id."""
        return self._tasks.get(task_id)

    async def list_tasks(self, user_id: str = None) -> list[BackgroundTask]:
        """List tasks, optionally filtered by user_id."""
        if user_id:
            return [t for t in self._tasks.values() if t.user_id == user_id]
        return list(self._tasks.values())

    async def start_worker(self) -> None:
        """Start the background worker loop."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("background_worker_started")

    async def stop_worker(self) -> None:
        """Stop the background worker loop."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            logger.info("background_worker_stopped")

    async def _worker_loop(self) -> None:
        """Background loop: dequeue task → create agent → execute → update status → notify."""
        while True:
            await self._worker_loop_once()

    async def _worker_loop_once(self) -> None:
        """Process a single task from the queue (for testability)."""
        task_id = await self._queue.get()
        task = self._tasks.get(task_id)
        if not task:
            self._queue.task_done()
            return

        task.status = BackgroundTaskStatus.RUNNING
        logger.info("background_task_started", task_id=task_id, name=task.name)

        try:
            # Create user context for the background task
            user_ctx = UserContext(
                user_id=task.user_id,
                role=UserRole.ADMIN,
                tenant_id="default",
                permissions=[],
                memory_path="",
                session_id=f"bg-{task_id}",
            )
            self.memory_manager.init_user(task.user_id)

            agent = create_agent_for_user(
                user_ctx, self.config, self.memory_manager,
                self.skill_manager, self.approval_checker, self.sandbox_runner,
            )
            result = agent.invoke(
                {"messages": [{"role": "user", "content": task.prompt}]},
                config={"configurable": {"context": user_ctx}},
            )

            # Extract response content
            response_content = ""
            for msg in result.get("messages", []):
                if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                    response_content = msg.content

            task.result = response_content[:500]  # Truncate for notification
            task.status = BackgroundTaskStatus.COMPLETED
            task.completed_at = datetime.now().isoformat()
            logger.info("background_task_completed", task_id=task_id)

        except Exception as e:
            task.status = BackgroundTaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now().isoformat()
            logger.error("background_task_failed", task_id=task_id, error=str(e))

        finally:
            self._queue.task_done()
