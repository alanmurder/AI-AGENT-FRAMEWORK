"""Unit tests for AutoEvolver — mock-based, no real LLM calls."""

import pytest
from unittest.mock import MagicMock

from harness.evolution.auto_evolve import AutoEvolver
from harness.evolution.types import EvolutionCheckResult, ThreeAgentResult
from harness.evolution.three_agent import ThreeAgentVerifier
from harness.multi_agent.subagent import SubAgentRunner
from harness.multi_agent.types import SubAgentResult, SubAgentRole
from harness.skill.manager import SkillManager
from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole


@pytest.fixture
def mock_runner():
    return MagicMock(spec=SubAgentRunner)


@pytest.fixture
def mock_verifier():
    return MagicMock(spec=ThreeAgentVerifier)


@pytest.fixture
def mock_skill_manager():
    sm = MagicMock()
    sm.list_skills.return_value = [
        {"name": "file_manager"},
        {"name": "knowledge_search"},
    ]
    return sm


@pytest.fixture
def config():
    return AgentConfig()


@pytest.fixture
def evolver(mock_runner, mock_verifier, mock_skill_manager, config):
    return AutoEvolver(mock_runner, mock_verifier, mock_skill_manager, config)


class TestCheckEvolutionNeed:
    """AutoEvolver.check_evolution_need tests."""

    def test_identifies_need_for_new_skill(self, evolver, mock_runner):
        mock_runner.spawn.return_value = SubAgentResult(
            task_id="se1", role=SubAgentRole.EVALUATOR,
            content="## Decision\nNEEDS_NEW_SKILL: true\n## Reason\nRepeated scheduling failures\n## Suggested Skill Name\nschedule_manager",
            success=True,
        )

        result = evolver.check_evolution_need("User repeatedly asked for scheduling, but no skill available", "user1")
        assert result.needs_evolution
        assert result.suggested_skill_name == "schedule_manager"

    def test_no_evolution_needed(self, evolver, mock_runner):
        mock_runner.spawn.return_value = SubAgentResult(
            task_id="se1", role=SubAgentRole.EVALUATOR,
            content="## Decision\nNEEDS_NEW_SKILL: false\n## Reason\nAll requests covered by existing skills\n## Suggested Skill Name\n",
            success=True,
        )

        result = evolver.check_evolution_need("User asked about files, which file_manager covers", "user1")
        assert not result.needs_evolution

    def test_analysis_failure(self, evolver, mock_runner):
        mock_runner.spawn.return_value = SubAgentResult(
            task_id="se1", role=SubAgentRole.EVALUATOR,
            content="", success=False, error="Model timeout",
        )

        result = evolver.check_evolution_need("Some conversation", "user1")
        assert not result.needs_evolution
        assert "Analysis failed" in result.reason


class TestAutoCreateSkill:
    """AutoEvolver.auto_create_skill delegates to ThreeAgentVerifier."""

    def test_delegates_to_verifier(self, evolver, mock_verifier, user_ctx=None):
        if user_ctx is None:
            user_ctx = UserContext(user_id="u1", role=UserRole.ADMIN, session_id="s1")
        mock_verifier.verify.return_value = ThreeAgentResult(
            passed=True, skill_content="Skill content", skill_spec="Spec",
            evaluation="Good", rounds=1, suggestions=[],
        )

        result = evolver.auto_create_skill("Create a scheduling skill", user_ctx)
        assert result.passed
        mock_verifier.verify.assert_called_once_with("Create a scheduling skill", user_ctx)


class TestEvolutionCheckResult:
    """EvolutionCheckResult Pydantic model."""

    def test_default_no_evolution(self):
        result = EvolutionCheckResult(needs_evolution=False)
        assert not result.needs_evolution
        assert result.reason == ""
        assert result.suggested_skill_name == ""

    def test_with_evolution_needed(self):
        result = EvolutionCheckResult(
            needs_evolution=True,
            reason="No scheduling skill available",
            suggested_skill_name="schedule_manager",
        )
        assert result.needs_evolution
        assert result.suggested_skill_name == "schedule_manager"