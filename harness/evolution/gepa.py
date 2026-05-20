"""GEPA Evolutionary Optimizer — prompt evolution search for Skill improvement."""

import uuid
import structlog

from runtime.config import AgentConfig
from runtime.context_schema import UserContext
from harness.multi_agent.types import SubAgentConfig, SubAgentRole
from harness.multi_agent.subagent import SubAgentRunner
from harness.evolution.types import GEPACandidate, GEPAResult

logger = structlog.get_logger()

EVAL_PROMPT = """You are a Skill Quality Evaluator. Evaluate this SKILL.md content on these criteria:
1. Clarity (1-10): Is the skill description clear and unambiguous?
2. Completeness (1-10): Does it cover all necessary steps and edge cases?
3. Actionability (1-10): Can an agent follow this skill and produce correct results?
Output format:
## Scores
- Clarity: N/10
- Completeness: N/10
- Actionability: N/10
## Overall: N/10"""

VARIANT_PROMPT = """You are a Skill Variant Generator. Improve the following SKILL.md content based on these suggestions:
{suggestions}

Keep the same structure (YAML frontmatter + Markdown body) but improve clarity, completeness, and actionability.
Output ONLY the improved SKILL.md content."""

SUGGESTION_PROMPT = """You are a Skill Improvement Analyst. Analyze this SKILL.md and suggest specific improvements.
Focus on: clarity, completeness, actionability. Output 3-5 concrete suggestions as a numbered list."""


class GEPAOptimizer:
    """GEPA-style evolutionary optimizer for Skill prompts."""

    def __init__(self, subagent_runner: SubAgentRunner, config: AgentConfig):
        self.runner = subagent_runner
        self.config = config
        self.max_candidates = getattr(config, "gepa_max_candidates", 3)

    def optimize_skill(self, skill_name: str, skill_content: str, parent_ctx: UserContext) -> GEPAResult:
        """Run GEPA optimization on an existing Skill.

        MVP strategy: single-round optimization — generate 1 variant + evaluate.
        Pareto multi-version left for future iterations.
        """
        # Step 1: Evaluate original skill
        original_score = self._evaluate_skill(skill_content, parent_ctx)
        logger.info("gepa_original_score", skill_name=skill_name, score=original_score)

        if original_score >= 8.0:
            return GEPAResult(optimized=False, original_score=original_score, candidates_count=0)

        # Step 2: Generate improvement suggestions
        suggestions = self._generate_suggestions(skill_content, parent_ctx)

        # Step 3: Generate candidate variants
        candidates: list[GEPACandidate] = []
        for i in range(self.max_candidates):
            variant = self._generate_variant(skill_content, suggestions, parent_ctx, variant_num=i + 1)
            if not variant:
                continue

            # Step 4: Evaluate each variant
            variant_score = self._evaluate_skill(variant, parent_ctx)
            candidate = GEPACandidate(
                variant_id=f"gepa-{skill_name}-v{i + 1}-{uuid.uuid4().hex[:4]}",
                content=variant,
                score=variant_score,
            )
            candidates.append(candidate)

        # Step 5: Pick best candidate
        if not candidates:
            return GEPAResult(optimized=False, original_score=original_score, candidates_count=0)

        best = max(candidates, key=lambda c: c.score)

        # Only deploy if improvement is meaningful (>0.5 point improvement)
        if best.score > original_score + 0.5:
            logger.info("gepa_optimized", skill_name=skill_name, original=original_score, improved=best.score)
            return GEPAResult(
                optimized=True,
                original_score=original_score,
                best_candidate=best,
                candidates_count=len(candidates),
            )

        return GEPAResult(optimized=False, original_score=original_score, candidates_count=len(candidates))

    def _evaluate_skill(self, skill_content: str, parent_ctx: UserContext) -> float:
        """Evaluate a Skill using Evaluator SubAgent, returns overall score."""
        config = SubAgentConfig(role=SubAgentRole.EVALUATOR, model_type="mini")
        prompt = EVAL_PROMPT + f"\n\nSKILL.md to evaluate:\n{skill_content}"
        result = self.runner.spawn(config, prompt, parent_ctx)

        if not result.success:
            return 0.0

        return self._extract_score(result.content)

    def _generate_suggestions(self, skill_content: str, parent_ctx: UserContext) -> str:
        """Generate improvement suggestions using Worker SubAgent."""
        config = SubAgentConfig(role=SubAgentRole.WORKER, model_type="mini")
        prompt = SUGGESTION_PROMPT + f"\n\nSKILL.md:\n{skill_content}"
        result = self.runner.spawn(config, prompt, parent_ctx)
        return result.content if result.success else "Improve clarity and completeness"

    def _generate_variant(self, skill_content: str, suggestions: str, parent_ctx: UserContext, variant_num: int = 1) -> str | None:
        """Generate an improved variant using Generator SubAgent."""
        config = SubAgentConfig(role=SubAgentRole.GENERATOR, model_type="mini")
        prompt = VARIANT_PROMPT.format(suggestions=suggestions) + f"\n\nOriginal SKILL.md:\n{skill_content}"
        result = self.runner.spawn(config, prompt, parent_ctx)
        return result.content if result.success else None

    def _extract_score(self, evaluation_text: str) -> float:
        """Extract overall score from evaluation output."""
        for line in evaluation_text.split("\n"):
            if "Overall" in line and "/10" in line:
                try:
                    score_str = line.split(":")[-1].strip().replace("/10", "").strip()
                    return float(score_str)
                except ValueError:
                    continue
        return 0.0