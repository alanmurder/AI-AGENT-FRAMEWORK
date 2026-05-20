"""Unit tests for ThreeAgentVerifier — mock-based, no real LLM calls."""

import pytest
from unittest.mock import MagicMock, patch

from harness.evolution.three_agent import ThreeAgentVerifier
from harness.evolution.types import ThreeAgentResult
from harness.multi_agent.types import SubAgentResult, SubAgentRole, SubAgentConfig
from harness.multi_agent.subagent import SubAgentRunner
from runtime.context_schema import UserContext, UserRole


@pytest.fixture
def mock_runner():
    runner = MagicMock(spec=SubAgentRunner)
    return runner


@pytest.fixture
def verifier(mock_runner):
    return ThreeAgentVerifier(mock_runner, max_rounds=3)


@pytest.fixture
def user_ctx():
    return UserContext(user_id="test_user", role=UserRole.ADMIN, session_id="test-session")


class TestThreeAgentVerifierFlow:
    """Full three-agent verification flow with mock SubAgent."""

    def test_planner_failure_returns_not_passed(self, verifier, mock_runner, user_ctx):
        mock_runner.spawn.return_value = SubAgentResult(
            task_id="sub-planner-abc",
            role=SubAgentRole.PLANNER,
            content="",
            success=False,
            error="Model unavailable",
        )
        result = verifier.verify("Create a scheduling skill", user_ctx)
        assert not result.passed
        assert result.rounds == 0
        assert "Planner failed" in result.evaluation

    def test_generator_failure_returns_not_passed(self, verifier, mock_runner, user_ctx):
        # Planner succeeds
        planner_result = SubAgentResult(
            task_id="sub-planner-abc", role=SubAgentRole.PLANNER,
            content="## Specification\nName: scheduling\n## Criteria\nCompleteness, Accuracy",
            success=True,
        )
        # Generator fails
        gen_result = SubAgentResult(
            task_id="sub-generator-def", role=SubAgentRole.GENERATOR,
            content="", success=False, error="Generation error",
        )

        mock_runner.spawn.side_effect = [planner_result, gen_result]
        result = verifier.verify("Create a scheduling skill", user_ctx)
        assert not result.passed
        assert "Generator failed" in result.evaluation

    def test_evaluator_score_passes(self, verifier, mock_runner, user_ctx):
        planner_result = SubAgentResult(
            task_id="sp1", role=SubAgentRole.PLANNER,
            content="## Specification\nScheduling skill\n## Criteria\nCompleteness",
            success=True,
        )
        gen_result = SubAgentResult(
            task_id="sg1", role=SubAgentRole.GENERATOR,
            content="---\nname: scheduling\n---\n# Scheduling Skill", success=True,
        )
        eval_result = SubAgentResult(
            task_id="se1", role=SubAgentRole.EVALUATOR,
            content="## Scores\n- Completeness: 8/10\n## Overall: 8/10\n## Suggestions\n- Add more details",
            success=True,
        )
        mock_runner.spawn.side_effect = [planner_result, gen_result, eval_result]

        result = verifier.verify("Create scheduling skill", user_ctx)
        assert result.passed
        assert result.rounds == 1

    def test_evaluator_iteration_until_pass(self, verifier, mock_runner, user_ctx):
        """Evaluator fails round 1, passes round 2 after suggestions."""
        planner_result = SubAgentResult(
            task_id="sp1", role=SubAgentRole.PLANNER,
            content="## Specification\nScheduling\n## Criteria\nCompleteness", success=True,
        )
        # Round 1: Generator + Evaluator (score 5, not passed)
        gen1 = SubAgentResult(task_id="sg1", role=SubAgentRole.GENERATOR,
                             content="Basic skill content", success=True)
        eval1 = SubAgentResult(task_id="se1", role=SubAgentRole.EVALUATOR,
                              content="## Overall: 5/10\n## Suggestions\n- Add examples", success=True)
        # Round 2: Generator + Evaluator (score 8, passed)
        gen2 = SubAgentResult(task_id="sg2", role=SubAgentRole.GENERATOR,
                             content="Improved skill content", success=True)
        eval2 = SubAgentResult(task_id="se2", role=SubAgentRole.EVALUATOR,
                              content="## Overall: 8/10\n## Suggestions\n- Good now", success=True)

        mock_runner.spawn.side_effect = [planner_result, gen1, eval1, gen2, eval2]

        result = verifier.verify("Create scheduling skill", user_ctx)
        assert result.passed
        assert result.rounds == 2

    def test_max_rounds_reached(self, verifier, mock_runner, user_ctx):
        """Evaluator never reaches threshold, max rounds reached."""
        planner_result = SubAgentResult(
            task_id="sp1", role=SubAgentRole.PLANNER,
            content="## Specification\nScheduling\n## Criteria\nCompleteness", success=True,
        )
        low_eval = SubAgentResult(
            task_id="se1", role=SubAgentRole.EVALUATOR,
            content="## Overall: 4/10\n## Suggestions\n- Needs work", success=True,
        )
        gen_result = SubAgentResult(
            task_id="sg1", role=SubAgentRole.GENERATOR,
            content="Still basic content", success=True,
        )

        mock_runner.spawn.side_effect = [
            planner_result, gen_result, low_eval, gen_result, low_eval, gen_result, low_eval,
        ]

        result = verifier.verify("Create scheduling skill", user_ctx)
        assert not result.passed
        assert result.rounds == 3


class TestThreeAgentExtractMethods:
    """Test text extraction helpers."""

    def test_extract_criteria(self, verifier):
        text = "## Specification\nScheduling\n## Criteria\nCompleteness\nAccuracy\nUsability\n## Other"
        criteria = verifier._extract_criteria(text)
        assert "Completeness" in criteria
        assert "Accuracy" in criteria

    def test_extract_criteria_missing(self, verifier):
        text = "## Specification\nScheduling\n## Other"
        criteria = verifier._extract_criteria(text)
        assert "Completeness" in criteria  # Falls back to defaults

    def test_extract_overall_score(self, verifier):
        text = "## Overall: 7.5/10\n## Suggestions\n- Improve X"
        score = verifier._extract_overall_score(text)
        assert score == 7.5

    def test_extract_overall_score_missing(self, verifier):
        text = "No overall score here"
        score = verifier._extract_overall_score(text)
        assert score == 0.0

    def test_extract_suggestions(self, verifier):
        text = "## Scores\n- X: 5/10\n## Suggestions\n- Add examples\n- Improve clarity\n## Done"
        suggestions = verifier._extract_suggestions(text)
        assert "Add examples" in suggestions
        assert "Improve clarity" in suggestions