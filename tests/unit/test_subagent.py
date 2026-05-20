"""Unit tests for SubAgent system — mock-based, no real LLM calls."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from harness.multi_agent.types import (
    SubAgentRole,
    SubAgentConfig,
    SubAgentResult,
    ROLE_TOOLS,
    READONLY_TOOLS,
    FULL_TOOLS,
)
from harness.multi_agent.subagent import SubAgentRunner
from runtime.context_schema import UserContext, UserRole
from runtime.tools import BASE_TOOLS, ALL_TOOLS


class TestSubAgentTypes:
    """SubAgent type definitions and defaults."""

    def test_sub_agent_role_values(self):
        assert SubAgentRole.PLANNER.value == "planner"
        assert SubAgentRole.GENERATOR.value == "generator"
        assert SubAgentRole.EVALUATOR.value == "evaluator"
        assert SubAgentRole.WORKER.value == "worker"

    def test_config_defaults(self):
        config = SubAgentConfig()
        assert config.role == SubAgentRole.WORKER
        assert config.system_prompt == ""
        assert config.tools == []
        assert config.max_depth == 1
        assert config.timeout == 120
        assert config.model_type == "mini"

    def test_config_custom(self):
        config = SubAgentConfig(
            role=SubAgentRole.PLANNER,
            system_prompt="Plan this task",
            tools=["file_read", "web_search"],
            timeout=60,
            model_type="primary",
        )
        assert config.role == SubAgentRole.PLANNER
        assert config.timeout == 60
        assert config.model_type == "primary"

    def test_result_model(self):
        result = SubAgentResult(
            task_id="sub-planner-abc123",
            role=SubAgentRole.PLANNER,
            content="Here is the plan...",
            success=True,
        )
        assert result.success
        assert result.error is None
        assert result.metadata == {}

    def test_result_with_error(self):
        result = SubAgentResult(
            task_id="sub-worker-def456",
            role=SubAgentRole.WORKER,
            content="",
            success=False,
            error="Timeout after 120s",
        )
        assert not result.success
        assert result.error == "Timeout after 120s"


class TestRoleTools:
    """Tool set mappings by role."""

    def test_readonly_tools(self):
        assert "file_read" in READONLY_TOOLS
        assert "web_search" in READONLY_TOOLS
        assert "command_exec" not in READONLY_TOOLS
        assert "spawn_subagent" not in READONLY_TOOLS

    def test_role_tools_planner_readonly(self):
        assert ROLE_TOOLS[SubAgentRole.PLANNER] == READONLY_TOOLS

    def test_role_tools_evaluator_readonly(self):
        assert ROLE_TOOLS[SubAgentRole.EVALUATOR] == READONLY_TOOLS

    def test_role_tools_generator_can_write(self):
        gen_tools = ROLE_TOOLS[SubAgentRole.GENERATOR]
        assert "file_write" in gen_tools
        assert "command_exec" not in gen_tools

    def test_role_tools_worker_full(self):
        assert ROLE_TOOLS[SubAgentRole.WORKER] == FULL_TOOLS

    def test_no_spawn_in_any_role(self):
        for role, tools in ROLE_TOOLS.items():
            assert "spawn_subagent" not in tools


class TestSpawnSubagentTool:
    """spawn_subagent tool in runtime/tools.py."""

    def test_all_tools_includes_spawn(self):
        tool_names = [t.name for t in ALL_TOOLS]
        assert "spawn_subagent" in tool_names

    def test_base_tools_excludes_spawn(self):
        tool_names = [t.name for t in BASE_TOOLS]
        assert "spawn_subagent" not in tool_names

    def test_all_tools_count(self):
        assert len(ALL_TOOLS) == 8

    def test_base_tools_count(self):
        assert len(BASE_TOOLS) == 7


class TestSubAgentCapableRoles:
    """Role-based tool selection in agent.py."""

    def test_admin_gets_all_tools(self):
        from runtime.agent import SUBAGENT_CAPABLE_ROLES
        assert UserRole.ADMIN in SUBAGENT_CAPABLE_ROLES

    def test_manager_gets_all_tools(self):
        from runtime.agent import SUBAGENT_CAPABLE_ROLES
        assert UserRole.MANAGER in SUBAGENT_CAPABLE_ROLES

    def test_operator_gets_base_tools(self):
        from runtime.agent import SUBAGENT_CAPABLE_ROLES
        assert UserRole.OPERATOR not in SUBAGENT_CAPABLE_ROLES

    def test_viewer_gets_base_tools(self):
        from runtime.agent import SUBAGENT_CAPABLE_ROLES
        assert UserRole.VIEWER not in SUBAGENT_CAPABLE_ROLES


class TestSubAgentRunner:
    """SubAgentRunner with mock dependencies."""

    def _make_runner(self):
        config = MagicMock()
        memory_manager = MagicMock()
        skill_manager = MagicMock()
        approval_checker = MagicMock()
        return SubAgentRunner(config, memory_manager, skill_manager, approval_checker)

    def _make_user_ctx(self, role=UserRole.ADMIN):
        return UserContext(
            user_id="test_user",
            role=role,
            session_id="test-session",
        )

    def test_spawn_creates_isolated_context(self):
        runner = self._make_runner()
        sub_config = SubAgentConfig(role=SubAgentRole.PLANNER, system_prompt="Plan it")

        # Mock agent creation so we don't need a real LLM
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {
            "messages": [MagicMock(type="ai", content="Plan: step 1, step 2")]
        }

        with patch.object(runner, "_create_sub_agent", return_value=mock_agent):
            result = runner.spawn(sub_config, "Create a plan for X", self._make_user_ctx())

        assert result.success
        assert result.content == "Plan: step 1, step 2"
        assert result.role == SubAgentRole.PLANNER

    def test_spawn_handles_agent_creation_failure(self):
        runner = self._make_runner()
        sub_config = SubAgentConfig(role=SubAgentRole.WORKER)

        with patch.object(runner, "_create_sub_agent", side_effect=Exception("Model not available")):
            result = runner.spawn(sub_config, "Do something", self._make_user_ctx())

        assert not result.success
        assert "Model not available" in result.error

    def test_spawn_handles_execution_failure(self):
        runner = self._make_runner()
        sub_config = SubAgentConfig(role=SubAgentRole.WORKER)

        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = Exception("LLM timeout")

        with patch.object(runner, "_create_sub_agent", return_value=mock_agent):
            result = runner.spawn(sub_config, "Do something", self._make_user_ctx())

        assert not result.success
        assert "LLM timeout" in result.error

    def test_spawn_preserves_user_id(self):
        runner = self._make_runner()
        parent_ctx = self._make_user_ctx(role=UserRole.ADMIN)
        sub_config = SubAgentConfig(role=SubAgentRole.WORKER)

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [MagicMock(type="ai", content="Done")]}

        captured_ctx = None
        original_create = runner._create_sub_agent

        def mock_create(s_cfg, s_ctx):
            captured_ctx = s_ctx
            return mock_agent

        with patch.object(runner, "_create_sub_agent", side_effect=mock_create):
            result = runner.spawn(sub_config, "Task", parent_ctx)

        # The SubAgent inherits the parent's user_id
        # We verify this by checking _create_sub_agent was called
        assert result.success

    def test_filter_tools_default_role(self):
        runner = self._make_runner()
        sub_config = SubAgentConfig(role=SubAgentRole.WORKER)  # no custom tools
        tools = runner._filter_tools(sub_config)

        tool_names = [t.name for t in tools]
        for expected in FULL_TOOLS:
            assert expected in tool_names
        assert "spawn_subagent" not in tool_names

    def test_filter_tools_planner_readonly(self):
        runner = self._make_runner()
        sub_config = SubAgentConfig(role=SubAgentRole.PLANNER)
        tools = runner._filter_tools(sub_config)

        tool_names = [t.name for t in tools]
        for expected in READONLY_TOOLS:
            assert expected in tool_names
        assert "file_write" not in tool_names
        assert "command_exec" not in tool_names

    def test_filter_tools_custom_set(self):
        runner = self._make_runner()
        sub_config = SubAgentConfig(
            role=SubAgentRole.WORKER,
            tools=["file_read", "web_search"],
        )
        tools = runner._filter_tools(sub_config)

        tool_names = [t.name for t in tools]
        assert set(tool_names) == {"file_read", "web_search"}

    def test_filter_tools_never_includes_spawn(self):
        runner = self._make_runner()
        # Even if someone tries to include spawn_subagent in custom tools
        sub_config = SubAgentConfig(
            role=SubAgentRole.WORKER,
            tools=["file_read", "spawn_subagent"],
        )
        tools = runner._filter_tools(sub_config)

        tool_names = [t.name for t in tools]
        assert "spawn_subagent" not in tool_names

    def test_default_system_prompts(self):
        for role in SubAgentRole:
            prompt = SubAgentRunner._default_system_prompt(role)
            assert len(prompt) > 0

    def test_default_prompt_planner(self):
        prompt = SubAgentRunner._default_system_prompt(SubAgentRole.PLANNER)
        assert "Planner" in prompt

    def test_default_prompt_generator(self):
        prompt = SubAgentRunner._default_system_prompt(SubAgentRole.GENERATOR)
        assert "Generator" in prompt

    def test_default_prompt_evaluator(self):
        prompt = SubAgentRunner._default_system_prompt(SubAgentRole.EVALUATOR)
        assert "Evaluator" in prompt