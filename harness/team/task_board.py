"""TaskBoard — shared task queue with dependency tracking and claim mechanism."""

import uuid
import structlog
from datetime import datetime

from harness.team.types import TaskItem, TaskStatus, TaskBoard

logger = structlog.get_logger()


class TaskBoardManager:
    """In-memory TaskBoard manager — create, claim, submit, dependency check."""

    def __init__(self, config):
        self.config = config
        self._boards: dict[str, TaskBoard] = {}

    def _ensure_board(self, board_id: str) -> TaskBoard:
        if board_id not in self._boards:
            self._boards[board_id] = TaskBoard(board_id=board_id)
        return self._boards[board_id]

    def create_task(
        self,
        board_id: str,
        description: str,
        role_prompt: str,
        context: str = "",
        assignee: str = "",
        dependencies: list[str] = [],
    ) -> str:
        """Create a new task on the board, returns task_id."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        board = self._ensure_board(board_id)

        status = TaskStatus.PENDING
        if assignee:
            status = TaskStatus.CLAIMED
        elif dependencies:
            all_done = all(
                board.tasks.get(d) and board.tasks[d].status == TaskStatus.COMPLETED
                for d in dependencies
            )
            if not all_done:
                status = TaskStatus.BLOCKED

        task = TaskItem(
            task_id=task_id,
            description=description,
            role_prompt=role_prompt,
            context=context,
            status=status,
            assignee=assignee if assignee else None,
            dependencies=dependencies,
            created_at=datetime.now().isoformat(),
        )
        board.tasks[task_id] = task
        logger.info("task_created", task_id=task_id, board_id=board_id, status=status.value)
        return task_id

    def claim_task(self, board_id: str, task_id: str, agent_id: str) -> bool:
        """Claim a pending task for a member."""
        board = self._ensure_board(board_id)
        task = board.tasks.get(task_id)
        if not task or task.status not in (TaskStatus.PENDING, TaskStatus.BLOCKED):
            return False
        if task.status == TaskStatus.BLOCKED and not self.can_claim(board_id, task_id):
            return False
        task.status = TaskStatus.CLAIMED
        task.assignee = agent_id
        logger.info("task_claimed", task_id=task_id, agent_id=agent_id)
        return True

    def submit_result(self, board_id: str, task_id: str, result: str) -> None:
        """Submit a task result and mark as completed."""
        board = self._ensure_board(board_id)
        task = board.tasks.get(task_id)
        if not task:
            return
        task.result = result
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        logger.info("task_completed", task_id=task_id)

        # Unblock dependent tasks
        for other_task in board.tasks.values():
            if other_task.status == TaskStatus.BLOCKED and task_id in other_task.dependencies:
                all_deps_done = all(
                    board.tasks.get(d) and board.tasks[d].status == TaskStatus.COMPLETED
                    for d in other_task.dependencies
                )
                if all_deps_done:
                    other_task.status = TaskStatus.PENDING

    def get_task(self, board_id: str, task_id: str) -> TaskItem | None:
        """Get a specific task."""
        board = self._ensure_board(board_id)
        return board.tasks.get(task_id)

    def list_tasks(self, board_id: str) -> list[TaskItem]:
        """List all tasks on a board."""
        board = self._ensure_board(board_id)
        return list(board.tasks.values())

    def can_claim(self, board_id: str, task_id: str) -> bool:
        """Check if a task can be claimed (all dependencies completed)."""
        board = self._ensure_board(board_id)
        task = board.tasks.get(task_id)
        if not task:
            return False
        if not task.dependencies:
            return True
        return all(
            board.tasks.get(d) and board.tasks[d].status == TaskStatus.COMPLETED
            for d in task.dependencies
        )