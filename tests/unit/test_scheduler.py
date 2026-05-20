"""Scheduler module tests — Heartbeat and Cron."""

import pytest
from harness.scheduler.heartbeat import HeartbeatScheduler
from harness.scheduler.cron import CronScheduler, create_cron_task
from harness.scheduler.types import CronTask, HeartbeatResult, TaskStatus, TaskType
from runtime.config import AgentConfig


@pytest.fixture
def config():
    return AgentConfig()


@pytest.fixture
def heartbeat(config):
    return HeartbeatScheduler(config, interval_minutes=30)


@pytest.fixture
def cron(config):
    return CronScheduler(config)


class TestSchedulerTypes:
    def test_task_type_values(self):
        assert TaskType.HEARTBEAT == "heartbeat"
        assert TaskType.CRON == "cron"

    def test_task_status_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"

    def test_cron_task_creation(self):
        task = CronTask(
            task_id="cron-abc123",
            name="Daily Report",
            cron_expression="0 9 * * *",
            user_id="user1",
            prompt="Generate daily production report",
        )
        assert task.task_id == "cron-abc123"
        assert task.status == TaskStatus.PENDING
        assert task.channel == "web"

    def test_heartbeat_result_creation(self):
        result = HeartbeatResult(
            user_id="user1",
            timestamp="2026-05-12T10:00:00",
            summary="All systems normal",
        )
        assert result.user_id == "user1"
        assert result.anomalies == []
        assert result.actions_taken == []


class TestHeartbeatScheduler:
    def test_init(self, heartbeat, config):
        assert heartbeat.config == config
        assert heartbeat.interval_minutes == 30

    def test_register_user_callback(self, heartbeat):
        results = []
        heartbeat.register_user("user1", lambda r: results.append(r))
        assert "user1" in heartbeat._user_callbacks

    def test_register_multiple_users(self, heartbeat):
        heartbeat.register_user("user1", lambda r: None)
        heartbeat.register_user("user2", lambda r: None)
        assert len(heartbeat._user_callbacks) == 2

    def test_start_stop(self, heartbeat):
        heartbeat.start()
        # Verify scheduler is running
        assert heartbeat._scheduler.running
        heartbeat.stop()

    def test_start_stop_idempotent(self, heartbeat):
        heartbeat.start()
        heartbeat.stop()
        # Stopping an already stopped scheduler should not crash


class TestCronScheduler:
    def test_init(self, cron, config):
        assert cron.config == config

    def test_parse_valid_cron_expression(self, cron):
        kwargs = cron._parse_cron_expression("0 9 * * *")
        assert kwargs == {"minute": "0", "hour": "9", "day": "*", "month": "*", "day_of_week": "*"}

    def test_parse_complex_cron(self, cron):
        kwargs = cron._parse_cron_expression("*/5 8-18 * * 1-5")
        assert kwargs["minute"] == "*/5"
        assert kwargs["hour"] == "8-18"
        assert kwargs["day_of_week"] == "1-5"

    def test_parse_invalid_cron_fewer_fields(self, cron):
        with pytest.raises(ValueError, match="Expected 5 fields"):
            cron._parse_cron_expression("0 9 * *")

    def test_parse_invalid_cron_more_fields(self, cron):
        with pytest.raises(ValueError, match="Expected 5 fields"):
            cron._parse_cron_expression("0 9 * * * 2026")

    def test_add_task(self, cron):
        task = CronTask(
            task_id="cron-test1",
            name="Test Task",
            cron_expression="0 9 * * *",
            user_id="user1",
            prompt="Check system status",
        )
        cron.add_task(task)
        assert "cron-test1" in cron._tasks
        assert task.status == TaskStatus.PENDING

    def test_remove_task(self, cron):
        task = CronTask(
            task_id="cron-test2",
            name="Remove Test",
            cron_expression="0 9 * * *",
            user_id="user1",
            prompt="Test",
        )
        cron.add_task(task)
        removed = cron.remove_task("cron-test2")
        assert removed is True
        assert "cron-test2" not in cron._tasks

    def test_remove_nonexistent_task(self, cron):
        removed = cron.remove_task("cron-nonexistent")
        assert removed is False

    def test_list_tasks_all(self, cron):
        task1 = CronTask(task_id="t1", name="Task1", cron_expression="0 9 * * *", user_id="user1", prompt="P1")
        task2 = CronTask(task_id="t2", name="Task2", cron_expression="0 18 * * *", user_id="user2", prompt="P2")
        cron.add_task(task1)
        cron.add_task(task2)
        all_tasks = cron.list_tasks()
        assert len(all_tasks) == 2

    def test_list_tasks_by_user(self, cron):
        task1 = CronTask(task_id="t1", name="Task1", cron_expression="0 9 * * *", user_id="user1", prompt="P1")
        task2 = CronTask(task_id="t2", name="Task2", cron_expression="0 18 * * *", user_id="user2", prompt="P2")
        cron.add_task(task1)
        cron.add_task(task2)
        user1_tasks = cron.list_tasks(user_id="user1")
        assert len(user1_tasks) == 1
        assert user1_tasks[0].task_id == "t1"

    def test_get_task(self, cron):
        task = CronTask(task_id="t3", name="Task3", cron_expression="0 9 * * *", user_id="user1", prompt="P3")
        cron.add_task(task)
        found = cron.get_task("t3")
        assert found is not None
        assert found.name == "Task3"

    def test_get_nonexistent_task(self, cron):
        found = cron.get_task("cron-nonexistent")
        assert found is None

    def test_register_callback(self, cron):
        task = CronTask(task_id="t4", name="Task4", cron_expression="0 9 * * *", user_id="user1", prompt="P4")
        cron.add_task(task)
        results = []
        cron.register_callback("t4", lambda r: results.append(r))

    def test_start_stop(self, cron):
        cron.start()
        assert cron._scheduler.running
        cron.stop()


class TestCreateCronTask:
    def test_factory_creates_task(self):
        task = create_cron_task(
            name="Daily Report",
            cron_expression="0 9 * * *",
            user_id="user1",
            prompt="Generate daily report",
        )
        assert task.task_id.startswith("cron-")
        assert task.name == "Daily Report"
        assert task.cron_expression == "0 9 * * *"
        assert task.channel == "web"
        assert task.status == TaskStatus.PENDING

    def test_factory_with_custom_channel(self):
        task = create_cron_task(
            name="Alert",
            cron_expression="*/10 * * * *",
            user_id="user1",
            prompt="Check alerts",
            channel="dingtalk",
        )
        assert task.channel == "dingtalk"