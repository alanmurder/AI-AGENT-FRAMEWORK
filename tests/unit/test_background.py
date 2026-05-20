"""Unit tests for BackgroundTaskManager — mock-based, no real LLM calls."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from harness.multi_agent.background import (
    BackgroundTaskManager,
    BackgroundTask,
    BackgroundTaskStatus,
)
from runtime.config import AgentConfig


@pytest.fixture
def config():
    return AgentConfig()


@pytest.fixture
def mock_deps():
    memory_manager = MagicMock()
    skill_manager = MagicMock()
    approval_checker = MagicMock()
    sandbox_runner = MagicMock()
    return memory_manager, skill_manager, approval_checker, sandbox_runner


@pytest.fixture
def bg_manager(config, mock_deps):
    mm, sm, ac, sr = mock_deps
    return BackgroundTaskManager(config, mm, sm, ac, sr)


class TestBackgroundTaskModel:
    """BackgroundTask Pydantic model tests."""

    def test_default_status(self):
        task = BackgroundTask(task_id="bg-abc", name="test", user_id="u1", prompt="hello")
        assert task.status == BackgroundTaskStatus.PENDING

    def test_completed_task(self):
        task = BackgroundTask(
            task_id="bg-abc", name="test", user_id="u1", prompt="hello",
            status=BackgroundTaskStatus.COMPLETED, result="done",
        )
        assert task.status == BackgroundTaskStatus.COMPLETED
        assert task.result == "done"

    def test_failed_task(self):
        task = BackgroundTask(
            task_id="bg-abc", name="test", user_id="u1", prompt="hello",
            status=BackgroundTaskStatus.FAILED, error="timeout",
        )
        assert task.error == "timeout"


class TestBackgroundTaskManager:
    """BackgroundTaskManager core operations."""

    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self, bg_manager):
        task_id = await bg_manager.submit(name="test_task", prompt="analyze data", user_id="user1")
        assert task_id.startswith("bg-")
        assert len(task_id) > 3

    @pytest.mark.asyncio
    async def test_get_status_after_submit(self, bg_manager):
        task_id = await bg_manager.submit(name="test", prompt="hello", user_id="u1")
        task = await bg_manager.get_status(task_id)
        assert task is not None
        assert task.task_id == task_id
        assert task.status == BackgroundTaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_status_nonexistent(self, bg_manager):
        task = await bg_manager.get_status("nonexistent")
        assert task is None

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, bg_manager):
        tasks = await bg_manager.list_tasks()
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_list_tasks_by_user(self, bg_manager):
        await bg_manager.submit(name="t1", prompt="p1", user_id="u1")
        await bg_manager.submit(name="t2", prompt="p2", user_id="u2")
        await bg_manager.submit(name="t3", prompt="p3", user_id="u1")

        tasks_u1 = await bg_manager.list_tasks(user_id="u1")
        assert len(tasks_u1) == 2

        tasks_all = await bg_manager.list_tasks()
        assert len(tasks_all) == 3

    @pytest.mark.asyncio
    async def test_worker_starts_and_stops(self, bg_manager):
        await bg_manager.start_worker()
        assert bg_manager._worker_task is not None
        assert not bg_manager._worker_task.done()

        await bg_manager.stop_worker()
        assert bg_manager._worker_task.done() if bg_manager._worker_task else True

    @pytest.mark.asyncio
    async def test_worker_loop_processes_task(self, bg_manager):
        """Test worker loop creates agent and processes task."""
        task_id = await bg_manager.submit(name="test", prompt="hello", user_id="u1")

        # Mock agent creation
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {
            "messages": [MagicMock(type="ai", content="Response from background agent")]
        }

        with patch("harness.multi_agent.background.create_agent_for_user", return_value=mock_agent):
            await bg_manager._worker_loop_once()

        task = await bg_manager.get_status(task_id)
        assert task.status == BackgroundTaskStatus.COMPLETED
        assert "Response from background agent" in task.result