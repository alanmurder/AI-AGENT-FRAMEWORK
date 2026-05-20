"""Auto-evolver — identifies Skill gaps and creates new Skills through three-agent verification."""

import structlog

from runtime.config import AgentConfig
from runtime.context_schema import UserContext
from harness.evolution.three_agent import ThreeAgentVerifier
from harness.evolution.types import EvolutionCheckResult, ThreeAgentResult
from harness.skill.manager import SkillManager
from harness.multi_agent.subagent import SubAgentRunner
from harness.multi_agent.types import SubAgentConfig, SubAgentRole

logger = structlog.get_logger()

CHECK_EVOLUTION_PROMPT = """You are a Skill Gap Analyst. Analyze this conversation summary and determine if a new Skill should be created.

Check:
1. Were there repeated failed requests or patterns the agent couldn't handle well?
2. Is there a domain/task area not covered by existing Skills?
3. Would a new Skill significantly improve future handling of similar requests?

Existing Skills: {skill_list}

Output format:
## Decision
NEEDS_NEW_SKILL: true/false
## Reason
(your reasoning)
## Suggested Skill Name
(name if needed, empty if not)"""


class AutoEvolver:
    """Identifies Skill gaps from conversation summaries and auto-creates Skills."""

    def __init__(
        self,
        subagent_runner: SubAgentRunner,
        three_agent_verifier: ThreeAgentVerifier,
        skill_manager: SkillManager,
        config: AgentConfig,
    ):
        self.runner = subagent_runner
        self.verifier = three_agent_verifier
        self.skill_manager = skill_manager
        self.config = config

    def check_evolution_need(self, conversation_summary: str, user_id: str) -> EvolutionCheckResult:
        """Analyze conversation summary to determine if a new Skill is needed."""
        skill_list = self._get_skill_names()

        prompt = CHECK_EVOLUTION_PROMPT.format(skill_list=skill_list) + f"\n\nConversation Summary:\n{conversation_summary}"

        config = SubAgentConfig(role=SubAgentRole.EVALUATOR, model_type="mini")
        result = self.runner.spawn(config, prompt, self._make_system_ctx(user_id))

        if not result.success:
            return EvolutionCheckResult(needs_evolution=False, reason=f"Analysis failed: {result.error}")

        return self._parse_check_result(result.content)

    def auto_create_skill(self, requirement: str, parent_ctx: UserContext) -> ThreeAgentResult:
        """Auto-create a Skill through three-agent verification."""
        return self.verifier.verify(requirement, parent_ctx)

    def _get_skill_names(self) -> str:
        """Get list of existing Skill names."""
        skills = self.skill_manager.list_skills()
        if not skills:
            return "(no skills registered)"
        return ", ".join([s["name"] for s in skills])

    def _make_system_ctx(self, user_id: str) -> UserContext:
        """Create a system UserContext for evolution operations."""
        from runtime.context_schema import UserRole
        return UserContext(
            user_id=user_id,
            role=UserRole.ADMIN,
            tenant_id="default",
            permissions=[],
            memory_path="",
            session_id=f"evolve-{user_id}",
        )

    def _parse_check_result(self, analysis_text: str) -> EvolutionCheckResult:
        """Parse the evolution check result from LLM output."""
        needs_evolution = False
        reason = ""
        suggested_name = ""
        current_section = ""

        for line in analysis_text.split("\n"):
            line = line.strip()
            if "NEEDS_NEW_SKILL:" in line:
                value = line.split("NEEDS_NEW_SKILL:")[-1].strip().lower()
                needs_evolution = value == "true"
            elif "## Reason" in line:
                current_section = "reason"
            elif "## Suggested Skill Name" in line:
                current_section = "name"
            elif line.startswith("##") and current_section:
                current_section = ""
            elif line and current_section == "reason":
                reason = line if not line.startswith("-") else line.lstrip("- ").strip()
                current_section = ""  # Only take first reason line
            elif line and current_section == "name" and not suggested_name:
                suggested_name = line.strip()

        return EvolutionCheckResult(
            needs_evolution=needs_evolution,
            reason=reason or "Identified Skill gap from conversation",
            suggested_skill_name=suggested_name,
        )