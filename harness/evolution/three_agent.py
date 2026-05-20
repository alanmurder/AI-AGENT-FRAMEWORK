"""Three-Agent Verifier — Planner→Generator→Evaluator for Skill quality control."""

import json
import structlog

from runtime.config import AgentConfig
from runtime.context_schema import UserContext
from harness.multi_agent.types import SubAgentConfig, SubAgentRole
from harness.multi_agent.subagent import SubAgentRunner
from harness.evolution.types import ThreeAgentResult

logger = structlog.get_logger()

PLANNER_PROMPT = """You are a Skill Planner. Analyze the user's requirement and produce:
1. A Skill specification (name, description, category, steps, tools needed)
2. Validation criteria (what makes this Skill good/bad)
Output as structured text with sections: ## Specification and ## Criteria."""

GENERATOR_PROMPT = """You are a Skill Generator. Given a Skill specification, create the complete SKILL.md content.
Follow the standard SKILL.md format with YAML frontmatter and Markdown body.
Output ONLY the SKILL.md content, nothing else."""

EVALUATOR_PROMPT = """You are a Skill Evaluator. Evaluate the following SKILL.md against these criteria:
{criteria}
Score each criterion 1-10, then give an overall score. Provide specific improvement suggestions.
Output format:
## Scores
- criterion1: N/10
- criterion2: N/10
## Overall: N/10
## Suggestions
- suggestion1
- suggestion2"""


class ThreeAgentVerifier:
    """Three-agent verification: Planner→Generator→Evaluator with iterative improvement."""

    def __init__(self, subagent_runner: SubAgentRunner, max_rounds: int = 3):
        self.runner = subagent_runner
        self.max_rounds = max_rounds

    def verify(self, requirement: str, parent_ctx: UserContext) -> ThreeAgentResult:
        """Run three-agent verification flow for a Skill requirement."""
        # Round 1: Planner produces specification and criteria
        spec_result = self._run_planner(requirement, parent_ctx)
        if not spec_result.success:
            return ThreeAgentResult(
                passed=False, skill_content="", skill_spec="",
                evaluation="Planner failed", rounds=0,
                suggestions=[spec_result.error or "Planner execution failed"],
            )

        spec_text = spec_result.content
        criteria = self._extract_criteria(spec_text)

        # Round 2+: Generator → Evaluator iteration
        suggestions: list[str] = []
        skill_content = ""
        evaluation_text = ""
        final_passed = False

        for round_num in range(self.max_rounds):
            gen_result = self._run_generator(spec_text, suggestions, parent_ctx)
            if not gen_result.success:
                return ThreeAgentResult(
                    passed=False, skill_content="", skill_spec=spec_text,
                    evaluation="Generator failed", rounds=round_num + 1,
                    suggestions=[gen_result.error or "Generator execution failed"],
                )

            skill_content = gen_result.content
            eval_result = self._run_evaluator(skill_content, criteria, parent_ctx)
            if not eval_result.success:
                return ThreeAgentResult(
                    passed=False, skill_content=skill_content, skill_spec=spec_text,
                    evaluation="Evaluator failed", rounds=round_num + 1,
                    suggestions=[eval_result.error or "Evaluator execution failed"],
                )

            evaluation_text = eval_result.content
            overall_score = self._extract_overall_score(evaluation_text)
            suggestions = self._extract_suggestions(evaluation_text)

            if overall_score >= 7:
                final_passed = True
                break

            # Not passed — inject improvement hints into next Generator round
            logger.info("three_agent_iterating", round=round_num + 1, score=overall_score)

        return ThreeAgentResult(
            passed=final_passed,
            skill_content=skill_content,
            skill_spec=spec_text,
            evaluation=evaluation_text,
            rounds=round_num + 1 if 'round_num' in dir() else self.max_rounds,
            suggestions=suggestions,
        )

    def _run_planner(self, requirement: str, parent_ctx: UserContext) -> "SubAgentResult":
        """Run Planner SubAgent to produce Skill specification."""
        config = SubAgentConfig(
            role=SubAgentRole.PLANNER,
            system_prompt=PLANNER_PROMPT,
            model_type="mini",
        )
        return self.runner.spawn(config, requirement, parent_ctx)

    def _run_generator(self, spec: str, suggestions: list[str], parent_ctx: UserContext) -> "SubAgentResult":
        """Run Generator SubAgent to create SKILL.md content."""
        prompt = f"Specification:\n{spec}"
        if suggestions:
            prompt += f"\n\nImprovement suggestions from previous evaluation:\n"
            for s in suggestions:
                prompt += f"- {s}\n"

        config = SubAgentConfig(
            role=SubAgentRole.GENERATOR,
            system_prompt=GENERATOR_PROMPT,
            model_type="mini",
        )
        return self.runner.spawn(config, prompt, parent_ctx)

    def _run_evaluator(self, skill_content: str, criteria: str, parent_ctx: UserContext) -> "SubAgentResult":
        """Run Evaluator SubAgent to evaluate SKILL.md content."""
        eval_prompt = EVALUATOR_PROMPT.format(criteria=criteria) + f"\n\nSKILL.md content to evaluate:\n{skill_content}"

        config = SubAgentConfig(
            role=SubAgentRole.EVALUATOR,
            system_prompt="",
            model_type="mini",
        )
        return self.runner.spawn(config, eval_prompt, parent_ctx)

    def _extract_criteria(self, spec_text: str) -> str:
        """Extract criteria section from Planner output."""
        lines = spec_text.split("\n")
        in_criteria = False
        criteria_lines = []
        for line in lines:
            if "## Criteria" in line or "## Validation Criteria" in line:
                in_criteria = True
                continue
            if in_criteria and line.startswith("##"):
                break
            if in_criteria:
                criteria_lines.append(line)
        return "\n".join(criteria_lines) if criteria_lines else "Completeness, Accuracy, Usability"

    def _extract_overall_score(self, evaluation_text: str) -> float:
        """Extract overall score from Evaluator output."""
        for line in evaluation_text.split("\n"):
            if "Overall" in line and "/10" in line:
                try:
                    score_str = line.split(":")[-1].strip().replace("/10", "").strip()
                    return float(score_str)
                except ValueError:
                    continue
        return 0.0

    def _extract_suggestions(self, evaluation_text: str) -> list[str]:
        """Extract improvement suggestions from Evaluator output."""
        lines = evaluation_text.split("\n")
        in_suggestions = False
        suggestions = []
        for line in lines:
            if "## Suggestions" in line:
                in_suggestions = True
                continue
            if in_suggestions and line.startswith("##"):
                break
            if in_suggestions and line.strip().startswith("-"):
                suggestions.append(line.strip().lstrip("- ").strip())
        return suggestions