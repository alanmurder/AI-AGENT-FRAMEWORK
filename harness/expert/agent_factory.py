"""Expert agent factory — creates Agent instances from AgentProfile."""

import structlog

from runtime.config import AgentConfig
from runtime.context_schema import UserContext
from runtime.models import create_primary_model, create_mini_model
from runtime.tools import BASE_TOOLS
from harness.expert.types import AgentProfile
from harness.memory.manager import MemoryManager
from harness.skill.manager import SkillManager
from harness.security.approval import ApprovalChecker
from harness.sandbox.runner import SandboxRunner
from harness.context.types import ContextConfig
from harness.context.compressor import ContextCompressor, build_context_config
from harness.context.flush import PreFlushMiddleware
from harness.middleware.memory_injection import MemoryInjectionMiddleware
from harness.middleware.auth_injection import AuthInjectionMiddleware
from harness.middleware.tool_filter import ToolFilterMiddleware
from harness.middleware.security_check import SecurityCheckMiddleware
from harness.middleware.output_validation import OutputValidationMiddleware
from harness.middleware.memory_archive import MemoryArchiveMiddleware
from harness.middleware.sandbox import SandboxMiddleware

logger = structlog.get_logger()


def create_expert_agent(
    profile: AgentProfile,
    soul_content: str,
    user_ctx: UserContext,
    config: AgentConfig,
    memory_manager: MemoryManager,
    skill_manager: SkillManager,
    approval_checker: ApprovalChecker,
    sandbox_runner: SandboxRunner | None = None,
):
    """Create a full Agent instance for an expert, with its own SOUL.md and Skill Plugin."""
    from langchain.agents import create_agent

    model = create_primary_model(config) if profile.model_preference == "primary" else create_mini_model(config)
    mini_model = create_mini_model(config)
    tools = BASE_TOOLS

    context_config = build_context_config(config)
    compressor = ContextCompressor(context_config, mini_model)

    system_prompt = soul_content or f"You are {profile.display_name}. {profile.description}"

    memory_manager.init_user(user_ctx.user_id)

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[
            AuthInjectionMiddleware(user_ctx),
            MemoryInjectionMiddleware(memory_manager, skill_manager, context_config, agent_config=config),
            compressor.create_summarization_middleware(),
            compressor.create_context_editing_middleware(),
            PreFlushMiddleware(memory_manager, context_config),
            ToolFilterMiddleware(),
            SecurityCheckMiddleware(approval_checker),
            SandboxMiddleware(sandbox_runner),
            OutputValidationMiddleware(),
            MemoryArchiveMiddleware(memory_manager, config=config),
        ],
        context_schema=UserContext,
    )
    return agent