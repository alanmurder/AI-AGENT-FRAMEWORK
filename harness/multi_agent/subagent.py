"""SubAgent runner — spawn independent agent instances for task delegation."""

import uuid
import structlog

from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole
from runtime.models import create_primary_model, create_mini_model
from runtime.tools import BASE_TOOLS
from harness.memory.manager import MemoryManager
from harness.skill.manager import SkillManager
from harness.security.approval import ApprovalChecker
from harness.sandbox.runner import SandboxRunner
from harness.multi_agent.types import (
    SubAgentConfig,
    SubAgentResult,
    SubAgentRole,
    ROLE_TOOLS,
    READONLY_TOOLS,
)

logger = structlog.get_logger()


class SubAgentRunner:
    """Manages SubAgent lifecycle — creates isolated agent instances for specific tasks."""

    def __init__(
        self,
        config: AgentConfig,
        memory_manager: MemoryManager,
        skill_manager: SkillManager,
        approval_checker: ApprovalChecker,
        sandbox_runner: SandboxRunner | None = None,
    ):
        self.config = config
        self.memory_manager = memory_manager
        self.skill_manager = skill_manager
        self.approval_checker = approval_checker
        self.sandbox_runner = sandbox_runner

    def spawn(self, sub_config: SubAgentConfig, task: str, parent_ctx: UserContext) -> SubAgentResult:
        """Create and run a SubAgent, blocking until result is ready.

        Args:
            sub_config: SubAgent configuration (role, tools, timeout, etc.)
            task: The task prompt for the SubAgent
            parent_ctx: Parent agent's UserContext (used for user_id, role inheritance)

        Returns:
            SubAgentResult with the SubAgent's output
        """
        task_id = f"sub-{sub_config.role.value}-{uuid.uuid4().hex[:8]}"
        session_id = f"subagent-{sub_config.role.value}-{uuid.uuid4().hex[:8]}"

        # Create isolated UserContext for the SubAgent
        sub_ctx = UserContext(
            user_id=parent_ctx.user_id,
            role=parent_ctx.role,
            tenant_id=parent_ctx.tenant_id,
            permissions=[],  # SubAgent gets no direct permissions — tools are filtered
            memory_path=parent_ctx.memory_path,
            session_id=session_id,
        )

        try:
            agent = self._create_sub_agent(sub_config, sub_ctx)
        except Exception as e:
            logger.error("subagent_create_failed", task_id=task_id, error=str(e))
            return SubAgentResult(
                task_id=task_id, role=sub_config.role, content="",
                success=False, error=f"Failed to create sub-agent: {e}",
            )

        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": task}]},
                config={"configurable": {"context": sub_ctx}},
            )

            # Extract AI response content
            ai_content = ""
            for msg in result.get("messages", []):
                if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                    ai_content = msg.content

            logger.info("subagent_completed", task_id=task_id, role=sub_config.role.value)
            return SubAgentResult(
                task_id=task_id, role=sub_config.role, content=ai_content,
                success=True,
            )

        except Exception as e:
            logger.error("subagent_execution_failed", task_id=task_id, error=str(e))
            return SubAgentResult(
                task_id=task_id, role=sub_config.role, content="",
                success=False, error=str(e),
            )

    def _create_sub_agent(self, sub_config: SubAgentConfig, sub_ctx: UserContext):
        """Create a LangChain agent instance for the SubAgent."""
        from langchain.agents import create_agent

        # Select model based on config
        if sub_config.model_type == "primary":
            model = create_primary_model(self.config)
        else:
            model = create_mini_model(self.config)

        # Filter tools based on SubAgent config
        filtered_tools = self._filter_tools(sub_config)

        # Build system prompt
        system_prompt = sub_config.system_prompt or self._default_system_prompt(sub_config.role)

        # Create agent with minimal middleware (no SubAgent middleware to prevent recursion)
        from harness.middleware.auth_injection import AuthInjectionMiddleware
        from harness.middleware.security_check import SecurityCheckMiddleware

        agent = create_agent(
            model=model,
            tools=filtered_tools,
            system_prompt=system_prompt,
            middleware=[
                AuthInjectionMiddleware(sub_ctx),
                SecurityCheckMiddleware(self.approval_checker),
            ],
            context_schema=UserContext,
        )
        return agent

    def _filter_tools(self, sub_config: SubAgentConfig) -> list:
        """Filter BASE_TOOLS based on SubAgent config."""
        # If custom tools specified, use those
        if sub_config.tools:
            allowed = set(sub_config.tools)
        else:
            # Default to role-based tools
            allowed = set(ROLE_TOOLS.get(sub_config.role, READONLY_TOOLS))

        # Never include spawn_subagent in SubAgent tools (prevent recursion)
        allowed.discard("spawn_subagent")

        # Filter BASE_TOOLS
        tool_map = {t.name: t for t in BASE_TOOLS}
        return [tool_map[name] for name in allowed if name in tool_map]

    @staticmethod
    def _default_system_prompt(role: SubAgentRole) -> str:
        """Generate default system prompt for each SubAgent role."""
        prompts = {
            SubAgentRole.PLANNER: "You are a Skill Planner. Analyze requirements and produce structured Skill specifications with validation criteria.",
            SubAgentRole.GENERATOR: "You are a Skill Generator. Create complete SKILL.md content from specifications, following the standard YAML frontmatter + Markdown format.",
            SubAgentRole.EVALUATOR: "You are a Skill Evaluator. Evaluate SKILL.md content against given criteria, score each criterion, and provide improvement suggestions.",
            SubAgentRole.WORKER: "You are a task execution assistant. Complete the assigned task efficiently and return results.",
        }
        return prompts.get(role, "You are a helpful assistant. Complete the assigned task.")
