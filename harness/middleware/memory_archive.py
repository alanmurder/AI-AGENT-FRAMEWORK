"""after_agent middleware — archives session to memory and triggers L1 evolution."""

from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from harness.memory.manager import MemoryManager
from harness.memory.types import MidTermSummaryType
from runtime.context_schema import UserContext
from runtime.config import AgentConfig


class MemoryArchiveMiddleware(AgentMiddleware):
    """After agent completes: archive conversation summary, trigger L1 evolution, write to PG."""

    def __init__(self, memory_manager: MemoryManager, config: AgentConfig = None):
        self.memory_manager = memory_manager
        self.config = config

    def _build_summary(self, messages: list) -> str:
        """Build a structured conversation summary from messages."""
        summary_parts = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str) and content:
                    summary_parts.append(f"User: {content[:300]}")
            elif isinstance(msg, AIMessage):
                content = msg.content
                if isinstance(content, str) and content and content.strip() and msg.name != "NO_REPLY":
                    summary_parts.append(f"Assistant: {content[:300]}")
                for tc in msg.tool_calls:
                    summary_parts.append(f"Assistant called tool: {tc['name']}({tc['args']})")
            elif isinstance(msg, ToolMessage):
                name = msg.name or "unknown"
                content_preview = str(msg.content)[:80] if msg.content else "(no output)"
                summary_parts.append(f"Tool result ({name}): {content_preview}")
        return "\n".join(summary_parts) if summary_parts else "(empty conversation)"

    def after_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Archive conversation to memory after agent run completes (sync)."""
        if runtime is None or runtime.context is None:
            return None

        user_ctx: UserContext = runtime.context
        messages = state.get("messages", [])

        conversation_summary = self._build_summary(messages)

        # L1 memory evolution: extract preferences/facts via LLM
        self.memory_manager.extract_and_save(user_ctx.user_id, conversation_summary)

        # PG write not available in sync context — async version handles it
        return None

    async def aafter_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Archive conversation to memory after agent run completes (async)."""
        if runtime is None or runtime.context is None:
            return None

        user_ctx: UserContext = runtime.context
        messages = state.get("messages", [])

        conversation_summary = self._build_summary(messages)

        # L1 memory evolution: extract preferences/facts via LLM
        self.memory_manager.extract_and_save(user_ctx.user_id, conversation_summary)

        # Write session summary to PG (mid-term memory)
        await self.memory_manager.write_mid_term(
            user_ctx.user_id,
            content=conversation_summary,
            summary_type=MidTermSummaryType.SESSION_SUMMARY,
            metadata={"session_id": user_ctx.session_id},
        )

        # Write extracted facts to PG as well
        if self.memory_manager.evolution:
            result = self.memory_manager.evolution.extract(conversation_summary)
            for fact in result.get("facts", []):
                await self.memory_manager.write_mid_term(
                    user_ctx.user_id,
                    content=fact,
                    summary_type=MidTermSummaryType.FACT,
                    metadata={"source": "session_summary"},
                )

        # Clear short-term session data
        await self.memory_manager.short_term.clear_session(user_ctx.user_id, user_ctx.session_id)

        # Phase 3: Auto-evolution check (if enabled)
        if self.config and getattr(self.config, "auto_evolve_enabled", False):
            try:
                from harness.evolution.auto_evolve import AutoEvolver
                from harness.multi_agent.subagent import SubAgentRunner
                from harness.skill.manager import SkillManager
                from harness.security.approval import ApprovalChecker
                from harness.evolution.three_agent import ThreeAgentVerifier

                subagent_runner = SubAgentRunner(self.config, memory_manager, SkillManager(self.config), ApprovalChecker())
                verifier = ThreeAgentVerifier(subagent_runner, max_rounds=self.config.three_agent_max_rounds)
                evolver = AutoEvolver(subagent_runner, verifier, SkillManager(self.config), self.config)

                check_result = evolver.check_evolution_need(conversation_summary, user_ctx.user_id)
                if check_result.needs_evolution:
                    logger.info("auto_evolution_triggered", user_id=user_ctx.user_id, skill_name=check_result.suggested_skill_name)
                    # Submit to background task manager for async execution (non-blocking)
                    try:
                        from gateway.server import background_manager
                        await background_manager.submit(
                            name=f"auto_evolve_{check_result.suggested_skill_name}",
                            prompt=f"Create a new Skill: {check_result.suggested_skill_name}. Requirement: {check_result.reason}",
                            user_id=user_ctx.user_id,
                        )
                    except Exception:
                        logger.warning("auto_evolve_background_submit_failed", error="background_manager not available")
            except Exception as e:
                logger.warning("auto_evolution_check_failed", error=str(e))

        return None