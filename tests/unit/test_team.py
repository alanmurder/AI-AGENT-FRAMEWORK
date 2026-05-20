"""Unit tests for Agent Teams — TaskBoard, TeamMemberPool, and TeamConfig."""

import pytest
import tempfile
from pathlib import Path

from harness.team.types import (
    TaskStatus, TaskItem, TaskBoard, TeamMemberConfig, TeamConfig,
)
from harness.team.task_board import TaskBoardManager
from harness.team.member_pool import TeamMemberPool, TeamManager
from runtime.config import AgentConfig


@pytest.fixture
def config():
    return AgentConfig()


@pytest.fixture
def board_mgr(config):
    return TaskBoardManager(config)


class TestTaskStatus:
    def test_all_statuses(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.CLAIMED.value == "claimed"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.BLOCKED.value == "blocked"


class TestTaskItem:
    def test_default_values(self):
        item = TaskItem(task_id="t1", description="Do something", role_prompt="You are an analyst")
        assert item.status == TaskStatus.PENDING
        assert item.assignee is None
        assert item.dependencies == []
        assert item.result == ""

    def test_with_dependencies(self):
        item = TaskItem(task_id="t3", description="Final report", role_prompt="Writer", dependencies=["t1", "t2"])
        assert len(item.dependencies) == 2


class TestTaskBoardManager:
    def test_create_task(self, board_mgr):
        task_id = board_mgr.create_task(
            board_id="team-default",
            description="Query fault logs",
            role_prompt="You are a data analyst",
            context="Look for equipment anomalies",
            assignee="",
            dependencies=[],
        )
        assert task_id.startswith("task-")

    def test_claim_task(self, board_mgr):
        task_id = board_mgr.create_task("team-default", "Query logs", "Analyst")
        claimed = board_mgr.claim_task("team-default", task_id, "member-1")
        assert claimed is True
        task = board_mgr.get_task("team-default", task_id)
        assert task.status == TaskStatus.CLAIMED
        assert task.assignee == "member-1"

    def test_submit_result(self, board_mgr):
        task_id = board_mgr.create_task("team-default", "Query logs", "Analyst")
        board_mgr.claim_task("team-default", task_id, "member-1")
        board_mgr.submit_result("team-default", task_id, "Found 3 fault patterns")
        task = board_mgr.get_task("team-default", task_id)
        assert task.status == TaskStatus.COMPLETED
        assert "3 fault patterns" in task.result

    def test_list_tasks(self, board_mgr):
        board_mgr.create_task("team-default", "Task A", "Analyst")
        board_mgr.create_task("team-default", "Task B", "Writer")
        tasks = board_mgr.list_tasks("team-default")
        assert len(tasks) == 2

    def test_dependency_blocking(self, board_mgr):
        t1 = board_mgr.create_task("team-default", "Task 1", "A")
        t2 = board_mgr.create_task("team-default", "Task 2", "B", dependencies=[t1])
        can_claim = board_mgr.can_claim("team-default", t2)
        assert not can_claim

    def test_dependency_resolved(self, board_mgr):
        t1 = board_mgr.create_task("team-default", "Task 1", "A")
        t2 = board_mgr.create_task("team-default", "Task 2", "B", dependencies=[t1])
        board_mgr.claim_task("team-default", t1, "m1")
        board_mgr.submit_result("team-default", t1, "Done")
        can_claim = board_mgr.can_claim("team-default", t2)
        assert can_claim

    def test_blocked_auto_unblocks(self, board_mgr):
        t1 = board_mgr.create_task("team-default", "Task 1", "A")
        t2 = board_mgr.create_task("team-default", "Task 2", "B", dependencies=[t1])
        assert board_mgr.get_task("team-default", t2).status == TaskStatus.BLOCKED
        board_mgr.claim_task("team-default", t1, "m1")
        board_mgr.submit_result("team-default", t1, "Done")
        assert board_mgr.get_task("team-default", t2).status == TaskStatus.PENDING

    def test_assignee_on_create(self, board_mgr):
        task_id = board_mgr.create_task("team-default", "Task A", "Analyst", assignee="m1")
        task = board_mgr.get_task("team-default", task_id)
        assert task.status == TaskStatus.CLAIMED
        assert task.assignee == "m1"


class TestTeamConfig:
    def test_team_config(self):
        tc = TeamConfig(name="production_team", display_name="生产协调组", captain="default", members=["equipment_monitor", "quality_inspector"], description="Production coordination")
        assert tc.captain == "default"
        assert len(tc.members) == 2

    def test_team_config_defaults(self):
        tc = TeamConfig(name="test")
        assert tc.captain == "default"
        assert tc.members == []
        assert tc.display_name == ""


class TestTeamManager:
    def test_scan_teams(self):
        with tempfile.TemporaryDirectory() as tmp:
            teams_dir = Path(tmp) / "agents" / "teams"
            teams_dir.mkdir(parents=True)
            (teams_dir / "production_team.yaml").write_text("""name: production_team
display_name: 生产协调组
captain: default
members:
  - equipment_monitor
  - quality_inspector
description: 处理生产相关的综合问题
""", encoding="utf-8")
            tm = TeamManager(AgentConfig())
            teams = tm.scan_teams(Path(tmp))
            assert len(teams) == 1
            assert teams[0].name == "production_team"

    def test_scan_teams_from_project(self):
        from runtime.config import AgentConfig as AC
        c = AC()
        root = Path(c.project_root) if c.project_root else Path(__file__).parent.parent.parent
        tm = TeamManager(AgentConfig())
        teams = tm.scan_teams(root)
        assert len(teams) >= 1  # production_team.yaml exists
        assert teams[0].name == "production_team"


class TestTeamMemberPool:
    def test_spawn_member(self, config):
        pool = TeamMemberPool(config)
        member_id = pool.spawn_member(role_prompt="You are a data analyst")
        assert member_id.startswith("member-")

    def test_claim_from_pool(self, config):
        pool = TeamMemberPool(config)
        member_id = pool.spawn_member(role_prompt="Analyst")
        board_mgr = pool.task_board
        task_id = board_mgr.create_task("team-default", "Analyze data", "Analyst")
        claimed_task = pool.claim_task_for_member(member_id)
        assert claimed_task is not None
        assert claimed_task.task_id == task_id

    def test_idle_timeout_check(self, config):
        pool = TeamMemberPool(config)
        member_id = pool.spawn_member(role_prompt="Idle worker")
        idle = pool.check_idle_members()
        assert member_id not in idle  # Just created, not idle yet

    def test_shutdown_member(self, config):
        pool = TeamMemberPool(config)
        member_id = pool.spawn_member(role_prompt="Worker")
        pool.shutdown_member(member_id)
        assert member_id not in pool.members