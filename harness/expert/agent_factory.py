"""Expert agent factory — creates Agent instances from AgentProfile."""

import structlog
from pathlib import Path

from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole
from runtime.models import create_primary_model, create_mini_model
from runtime.tools import BASE_TOOLS
from harness.expert.types import AgentProfile
from harness.memory.manager import MemoryManager
from harness.skill.manager import SkillManager
from harness.security.approval import ApprovalChecker
from harness.sandbox.manager import SandboxManager
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
from harness.security.rbac import get_role_mcp_tool_access
from harness.observability.chat_process import SKILL_USE_PROTOCOL_INSTRUCTION

logger = structlog.get_logger()


def build_expert_system_prompt(profile: AgentProfile, soul_content: str) -> str:
    """Build an expert Agent prompt with the public Skill-use protocol."""
    base_prompt = soul_content or f"You are {profile.display_name}. {profile.description}"
    return (
        f"{base_prompt}\n\n"
        f"--- PUBLIC PROCESS EVENTS ---\n{SKILL_USE_PROTOCOL_INSTRUCTION}\n--- END PUBLIC PROCESS EVENTS ---"
    )


def create_expert_agent(
    profile: AgentProfile,
    soul_content: str,
    user_ctx: UserContext,
    config: AgentConfig,
    memory_manager: MemoryManager,
    skill_manager: SkillManager,
    approval_checker: ApprovalChecker,
    sandbox_runner: SandboxManager | None = None,
    mcp_manager=None,
):
    """Create a full Agent instance for an expert, with SOUL.md, Skills, and MCP tools."""
    from langchain.agents import create_agent

    model = create_primary_model(config) if profile.model_preference == "primary" else create_mini_model(config)
    mini_model = create_mini_model(config)

    # Start with base tools
    tools = list(BASE_TOOLS)

    # Add MCP tools from the agent's profile (role-filtered)
    if mcp_manager and profile.mcp_tools:
        role = UserRole(profile.role)
        role_mcp_access = get_role_mcp_tool_access()
        mcp_tools = mcp_manager.get_tools_for_role(role, role_mcp_access)
        # Further filter to only tools in the agent's explicit mcp_tools list
        for tool_fn in mcp_tools:
            from harness.mcp.manager import func_name_to_full_name
            full_name = func_name_to_full_name(tool_fn.name)
            if full_name in profile.mcp_tools:
                tools.append(tool_fn)

    context_config = build_context_config(config)
    compressor = ContextCompressor(context_config, mini_model)

    system_prompt = build_expert_system_prompt(profile, soul_content)

    memory_manager.init_user(user_ctx.user_id)

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[
            AuthInjectionMiddleware(user_ctx),
            MemoryInjectionMiddleware(memory_manager, skill_manager, context_config, agent_config=config, allowed_skills=profile.skills),
            PreFlushMiddleware(memory_manager, context_config),
            compressor.create_summarization_middleware(),
            compressor.create_context_editing_middleware(),
            ToolFilterMiddleware(),
            SecurityCheckMiddleware(approval_checker),
            SandboxMiddleware(sandbox_runner),
            OutputValidationMiddleware(),
            MemoryArchiveMiddleware(memory_manager, config=config),
        ],
        context_schema=UserContext,
    )
    return agent


def create_expert_agent_for_user(
    profile: AgentProfile,
    user_ctx: UserContext,
    config: AgentConfig,
    memory_manager: MemoryManager,
    skill_manager: SkillManager,
    approval_checker: ApprovalChecker,
    sandbox_runner: SandboxManager | None = None,
    mcp_manager=None,
):
    """Create an expert agent that operates under the agent's configured role.

    The expert agent inherits its own role for tool filtering, not the calling user's role.
    The calling user just needs authentication to access the agent.
    """
    import structlog
    _log = structlog.get_logger()

    # Use the agent profile's role for tool filtering
    from runtime.context_schema import UserRole
    agent_role = UserRole(profile.role) if profile.role else user_ctx.role

    expert_ctx = UserContext(
        user_id=user_ctx.user_id,
        tenant_id=user_ctx.tenant_id,
        role=agent_role,
        permissions=user_ctx.permissions,
        memory_path=user_ctx.memory_path,
        session_id=user_ctx.session_id,
        agent_id=profile.name,
    )

    registry_soul = AgentRegistry()
    soul = registry_soul.load_soul_content(profile.name, Path(config.project_root) if config.project_root else Path.cwd())

    return create_expert_agent(
        profile=profile,
        soul_content=soul,
        user_ctx=expert_ctx,
        config=config,
        memory_manager=memory_manager,
        skill_manager=skill_manager,
        approval_checker=approval_checker,
        sandbox_runner=sandbox_runner,
        mcp_manager=mcp_manager,
    )
