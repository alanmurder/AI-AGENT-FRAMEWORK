"""Agent creation — builds a configured agent instance for a specific user."""

from pathlib import Path

from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole
from runtime.tools import BASE_TOOLS, ALL_TOOLS, CAPTAIN_TOOLS
from runtime.models import create_primary_model, create_mini_model
from harness.memory.manager import MemoryManager
from harness.skill.manager import SkillManager
from harness.security.approval import ApprovalChecker
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
from harness.sandbox.manager import SandboxManager


# Roles that can use spawn_subagent tool
SUBAGENT_CAPABLE_ROLES = {UserRole.ADMIN, UserRole.MANAGER}

# Roles that can use captain team tools (delegate_task, collect_results)
CAPTAIN_CAPABLE_ROLES = {UserRole.ADMIN, UserRole.MANAGER}


def create_agent_for_user(
    user_ctx: UserContext,
    config: AgentConfig,
    memory_manager: MemoryManager,
    skill_manager: SkillManager,
    approval_checker: ApprovalChecker,
    sandbox_runner: SandboxManager | None = None,
    mcp_manager=None,
):
    """Create a configured agent instance for a specific user.

    Admin/Manager roles get captain team tools when team_enabled.
    MCP tools are added based on the user's role.
    """
    from langchain.agents import create_agent

    model = create_primary_model(config)
    mini_model = create_mini_model(config)

    # Select tools based on user role and team config
    if user_ctx.role in CAPTAIN_CAPABLE_ROLES and config.team_enabled:
        tools = list(CAPTAIN_TOOLS)
    elif user_ctx.role in SUBAGENT_CAPABLE_ROLES:
        tools = list(ALL_TOOLS)
    else:
        tools = list(BASE_TOOLS)

    # Add MCP tools for the user's role
    if mcp_manager:
        from harness.security.rbac import get_role_mcp_tool_access
        role_mcp_access = get_role_mcp_tool_access()
        mcp_tools = mcp_manager.get_tools_for_role(user_ctx.role, role_mcp_access)
        tools.extend(mcp_tools)

    context_config = build_context_config(config)
    compressor = ContextCompressor(context_config, mini_model)

    # Build system prompt — inject Team manifest if team is enabled for captains
    system_prompt = f"You are an enterprise AI assistant. You are helping user '{user_ctx.user_id}' with role '{user_ctx.role.value}'. Follow Skill instructions when available. Be professional and practical."

    if config.team_enabled and user_ctx.role in CAPTAIN_CAPABLE_ROLES:
        from harness.team.member_pool import TeamManager
        from harness.expert.registry import AgentRegistry
        root = Path(config.project_root)
        tm = TeamManager(config)
        teams = tm.scan_teams(root)
        if teams:
            team = teams[0]  # MVP: use first team
            registry = AgentRegistry()
            registry.scan_profiles(root / "agents")
            member_lines = []
            for m_name in team.members:
                p = registry.get(m_name)
                if p:
                    member_lines.append(f"- {p.name} ({p.display_name}): {p.description}")
            if member_lines:
                system_prompt += (
                    f"\n\n--- YOUR TEAM ---\n"
                    f"You are the captain of '{team.display_name}'. Available experts:\n"
                    + "\n".join(member_lines)
                    + "\nUse delegate_task to assign sub-tasks, read_task_board to check progress, collect_results to gather outputs.\n"
                    f"--- END TEAM ---"
                )

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[
            AuthInjectionMiddleware(user_ctx),
            MemoryInjectionMiddleware(memory_manager, skill_manager, context_config, agent_config=config),
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
