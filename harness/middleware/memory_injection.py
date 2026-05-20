"""before_model middleware — injects memory context, skill manifest, plugin manifest, and mid-term results."""

from typing import Any
from pathlib import Path

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.messages import SystemMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.runtime import Runtime

from harness.context.types import ContextConfig
from harness.memory.manager import MemoryManager
from harness.skill.manager import SkillManager
from runtime.config import AgentConfig
from runtime.context_schema import UserContext

_FLUSH_INSTRUCTION = (
    "You are nearing the token limit. Before your context gets compressed, "
    "please save any critical facts, decisions, or user preferences using the "
    "memory_manage tool. Write key information to USER.md and MEMORY.md."
)


class MemoryInjectionMiddleware(AgentMiddleware):
    """Injects memory context, skill manifest, and mid-term results into the model prompt.

    Also detects when the context is approaching the flush threshold and injects
    a save-key-info instruction.
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        skill_manager: SkillManager,
        context_config: ContextConfig | None = None,
        agent_config: AgentConfig = None,
    ):
        self.memory_manager = memory_manager
        self.skill_manager = skill_manager
        self.context_config = context_config or ContextConfig()
        self.agent_config = agent_config
        self._injected_sessions: set[str] = set()

    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Add memory context and skill manifest (sync version — no mid-term retrieval)."""
        if runtime is None or runtime.context is None:
            return None

        user_ctx: UserContext = runtime.context
        session_id = user_ctx.session_id

        injection_parts = []

        if session_id not in self._injected_sessions:
            memory_ctx = self.memory_manager.load_context(user_ctx.user_id)
            memory_prompt = memory_ctx.to_prompt_section()
            skill_manifest = self.skill_manager.generate_manifest(user_ctx.role.value)

            if memory_prompt:
                injection_parts.append(f"--- MEMORY CONTEXT ---\n{memory_prompt}\n--- END MEMORY ---")

            # Plugin manifest (Phase 3) — inject before Skill manifest if plugins > 3
            plugin_manifest = self._get_plugin_manifest()
            if plugin_manifest:
                injection_parts.append(f"--- AVAILABLE PLUGINS ---\n{plugin_manifest}\n--- END PLUGINS ---")

            if skill_manifest:
                injection_parts.append(f"--- AVAILABLE SKILLS ---\n{skill_manifest}\n--- END SKILLS ---")

            self._injected_sessions.add(session_id)

        # Flush instruction
        messages = state.get("messages", [])
        tokens = count_tokens_approximately(messages)
        if tokens >= self.context_config.flush_threshold * 0.9:
            injection_parts.append(f"--- FLUSH WARNING ---\n{_FLUSH_INSTRUCTION}\n--- END FLUSH ---")

        if not injection_parts:
            return None

        injection = "\n\n".join(injection_parts)
        return {"messages": [SystemMessage(content=injection)]}

    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Async version — includes mid-term memory retrieval from PG."""
        if runtime is None or runtime.context is None:
            return None

        user_ctx: UserContext = runtime.context
        session_id = user_ctx.session_id

        injection_parts = []

        if session_id not in self._injected_sessions:
            memory_ctx = self.memory_manager.load_context(user_ctx.user_id)

            # Mid-term memory retrieval
            mid_term_results = await self._retrieve_mid_term(user_ctx.user_id, state)
            memory_ctx.mid_term_results = mid_term_results

            memory_prompt = memory_ctx.to_prompt_section()
            skill_manifest = self.skill_manager.generate_manifest(user_ctx.role.value)

            if memory_prompt:
                injection_parts.append(f"--- MEMORY CONTEXT ---\n{memory_prompt}\n--- END MEMORY ---")

            # Plugin manifest (Phase 3) — inject before Skill manifest if plugins > 3
            plugin_manifest = self._get_plugin_manifest()
            if plugin_manifest:
                injection_parts.append(f"--- AVAILABLE PLUGINS ---\n{plugin_manifest}\n--- END PLUGINS ---")

            if skill_manifest:
                injection_parts.append(f"--- AVAILABLE SKILLS ---\n{skill_manifest}\n--- END SKILLS ---")

            self._injected_sessions.add(session_id)

        # Flush instruction
        messages = state.get("messages", [])
        tokens = count_tokens_approximately(messages)
        if tokens >= self.context_config.flush_threshold * 0.9:
            injection_parts.append(f"--- FLUSH WARNING ---\n{_FLUSH_INSTRUCTION}\n--- END FLUSH ---")

        if not injection_parts:
            return None

        injection = "\n\n".join(injection_parts)
        return {"messages": [SystemMessage(content=injection)]}

    async def _retrieve_mid_term(self, user_id: str, state: AgentState) -> list[str]:
        """Retrieve mid-term memory results based on intent detection."""
        messages = state.get("messages", [])
        top_k = self.memory_manager.config.mid_term_search_top_k

        if not messages:
            return await self.memory_manager.search_mid_term_recent(user_id, top_k=3, days=7)

        # Get last user message for keyword extraction
        last_user_msg = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and msg.content:
                last_user_msg = msg.content
                break

        if not last_user_msg or len(last_user_msg) < 5:
            return await self.memory_manager.search_mid_term_recent(user_id, top_k=3, days=7)

        return await self.memory_manager.search_mid_term(user_id, query=last_user_msg, top_k=top_k)

    def _get_plugin_manifest(self) -> str:
        """Generate plugin manifest for prompt injection (Phase 3)."""
        if not self.agent_config:
            return ""
        from harness.skill.plugin import PluginManager
        pm = PluginManager(self.skill_manager)
        if self.agent_config.project_root:
            root = Path(self.agent_config.project_root)
        else:
            root = Path(__file__).parent.parent.parent
        return pm.generate_plugin_manifest(root)