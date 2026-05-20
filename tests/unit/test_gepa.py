"""Unit tests for GEPAOptimizer — mock-based, no real LLM calls."""

import pytest
from unittest.mock import MagicMock, patch

from harness.evolution.gepa import GEPAOptimizer
from harness.evolution.types import GEPAResult, GEPACandidate
from harness.multi_agent.subagent import SubAgentRunner
from harness.multi_agent.types import SubAgentResult, SubAgentRole
from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole


@pytest.fixture
def mock_runner():
    runner = MagicMock(spec=SubAgentRunner)
    return runner


@pytest.fixture
def config():
    c = AgentConfig()
    c.gepa_max_candidates = 1  # Single candidate for simpler test mocking
    return c


@pytest.fixture
def optimizer(mock_runner, config):
    return GEPAOptimizer(mock_runner, config)


@pytest.fixture
def user_ctx():
    return UserContext(user_id="test_user", role=UserRole.ADMIN, session_id="test-session")


class TestGEPAOptimization:
    """GEPAOptimizer single-round optimization tests."""

    def test_high_score_no_optimization(self, optimizer, mock_runner, user_ctx):
        """Original skill is already good (>8.0), no optimization needed."""
        eval_result = SubAgentResult(
            task_id="se1", role=SubAgentRole.EVALUATOR,
            content="## Overall: 9.0/10\n## Suggestions\n- None needed", success=True,
        )
        mock_runner.spawn.return_value = eval_result

        result = optimizer.optimize_skill("good_skill", "Good skill content", user_ctx)
        assert not result.optimized
        assert result.original_score == 9.0
        assert result.candidates_count == 0

    def test_optimization_with_improvement(self, optimizer, mock_runner, user_ctx):
        """Skill has low score, variant improves it."""
        # Evaluation of original: score 4
        eval_original = SubAgentResult(
            task_id="se1", role=SubAgentRole.EVALUATOR,
            content="## Overall: 4/10\n## Suggestions\n- Needs work", success=True,
        )
        # Suggestions generation
        suggestions_result = SubAgentResult(
            task_id="sw1", role=SubAgentRole.WORKER,
            content="1. Add more examples\n2. Improve clarity", success=True,
        )
        # Variant generation
        variant_result = SubAgentResult(
            task_id="sg1", role=SubAgentRole.GENERATOR,
            content="Improved skill content", success=True,
        )
        # Evaluation of variant: score 7
        eval_variant = SubAgentResult(
            task_id="se2", role=SubAgentRole.EVALUATOR,
            content="## Overall: 7/10\n## Suggestions\n- Better", success=True,
        )

        mock_runner.spawn.side_effect = [eval_original, suggestions_result, variant_result, eval_variant]

        result = optimizer.optimize_skill("bad_skill", "Bad skill content", user_ctx)
        assert result.optimized
        assert result.original_score == 4.0
        assert result.best_candidate is not None
        assert result.best_candidate.score == 7.0

    def test_optimization_no_improvement(self, optimizer, mock_runner, user_ctx):
        """Variant doesn't improve enough (<0.5 improvement)."""
        eval_original = SubAgentResult(
            task_id="se1", role=SubAgentRole.EVALUATOR,
            content="## Overall: 6/10\n## Suggestions\n- Needs work", success=True,
        )
        suggestions_result = SubAgentResult(
            task_id="sw1", role=SubAgentRole.WORKER,
            content="1. Small improvement", success=True,
        )
        variant_result = SubAgentResult(
            task_id="sg1", role=SubAgentRole.GENERATOR,
            content="Slightly better content", success=True,
        )
        eval_variant = SubAgentResult(
            task_id="se2", role=SubAgentRole.EVALUATOR,
            content="## Overall: 6.3/10\n## Suggestions\n- Still similar", success=True,
        )

        mock_runner.spawn.side_effect = [eval_original, suggestions_result, variant_result, eval_variant]

        result = optimizer.optimize_skill("meh_skill", "Meh skill content", user_ctx)
        assert not result.optimized  # Only 0.3 improvement, needs > 0.5

    def test_variant_generation_failure(self, optimizer, mock_runner, user_ctx):
        """Generator SubAgent fails, no variants produced."""
        eval_original = SubAgentResult(
            task_id="se1", role=SubAgentRole.EVALUATOR,
            content="## Overall: 3/10\n## Suggestions\n- Needs work", success=True,
        )
        suggestions_result = SubAgentResult(
            task_id="sw1", role=SubAgentRole.WORKER,
            content="1. Improve", success=True,
        )
        variant_fail = SubAgentResult(
            task_id="sg1", role=SubAgentRole.GENERATOR,
            content="", success=False, error="Generation failed",
        )

        mock_runner.spawn.side_effect = [eval_original, suggestions_result, variant_fail]

        result = optimizer.optimize_skill("failing_skill", "Bad content", user_ctx)
        assert not result.optimized
        assert result.candidates_count == 0


class TestGEPATypes:
    """GEPA type definitions."""

    def test_gepa_candidate(self):
        candidate = GEPACandidate(
            variant_id="gepa-test-v1-abcd",
            content="Improved content",
            score=8.5,
            criteria_scores={"clarity": 9.0, "completeness": 8.0},
        )
        assert candidate.score == 8.5
        assert candidate.criteria_scores["clarity"] == 9.0

    def test_gepa_result_no_optimization(self):
        result = GEPAResult(optimized=False, original_score=8.0, candidates_count=0)
        assert not result.optimized
        assert result.best_candidate is None

    def test_gepa_result_with_improvement(self):
        best = GEPACandidate(variant_id="v1", content="Better", score=9.0)
        result = GEPAResult(optimized=True, original_score=6.0, best_candidate=best, candidates_count=3)
        assert result.optimized
        assert result.best_candidate.score == 9.0