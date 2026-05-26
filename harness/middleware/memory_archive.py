"""after_agent middleware — archives session to memory and triggers L1 evolution."""

import asyncio
import structlog
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from harness.memory.manager import MemoryManager
from harness.memory.types import MidTermSummaryType
from runtime.context_schema import UserContext
from runtime.config import AgentConfig

logger = structlog.get_logger()


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

    # ── Sync path (REST API) ──

    def after_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Archive conversation after agent run completes.

        Per-session operations (no LLM calls):
        - Write session summary to PG (L2)
        - Append daily log (L1)
        - Clear Redis session (L3)

        LLM-based memory extraction and evolution are deferred to
        MemoryHeartbeatTask (periodic batch processing).
        """
        if runtime is None or runtime.context is None:
            return None

        user_ctx: UserContext = runtime.context
        messages = state.get("messages", [])
        conversation_summary = self._build_summary(messages)

        self.memory_manager.log_daily(user_ctx.user_id, conversation_summary)
        self._run_async_archive(user_ctx.user_id, user_ctx.session_id, conversation_summary)

        return None

    # ── Async path (WebSocket) ──

    async def aafter_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Archive conversation after agent run completes (async)."""
        if runtime is None or runtime.context is None:
            return None

        user_ctx: UserContext = runtime.context
        messages = state.get("messages", [])
        conversation_summary = self._build_summary(messages)

        self.memory_manager.log_daily(user_ctx.user_id, conversation_summary)
        await self._archive_mid_and_short(user_ctx.user_id, user_ctx.session_id, conversation_summary)

        return None

    # ── Internal ──

    def _run_async_archive(self, user_id: str, session_id: str, summary: str) -> None:
        """Run L2/L3 archive tasks in a dedicated event loop (sync path)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Event loop already running — schedule and hope for the best
                import concurrent.futures
                future = concurrent.futures.Future()

                async def _run():
                    try:
                        await self._archive_mid_and_short(user_id, session_id, summary)
                        future.set_result(None)
                    except Exception as e:
                        future.set_exception(e)

                loop.call_soon_threadsafe(asyncio.ensure_future, _run())
                future.result(timeout=30)
                return
            loop.run_until_complete(self._archive_mid_and_short(user_id, session_id, summary))
        except RuntimeError:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._archive_mid_and_short(user_id, session_id, summary))
                loop.close()
            except Exception as e:
                logger.warning("memory_archive_sync_l2_failed", error=str(e))
        except Exception as e:
            logger.warning("memory_archive_sync_event_loop_error", error=str(e))

    async def _archive_mid_and_short(self, user_id: str, session_id: str, summary: str) -> None:
        """Write L2 (PG) and clear L3 (Redis).

        Only writes session_summary — LLM-based fact extraction is deferred
        to MemoryHeartbeatTask for batch processing.
        """
        # L2: PG session summary (cheap INSERT, no LLM)
        await self.memory_manager.write_mid_term(
            user_id,
            content=summary,
            summary_type=MidTermSummaryType.SESSION_SUMMARY,
            metadata={"session_id": session_id},
        )

        # L3: clear Redis session
        await self.memory_manager.short_term.clear_session(user_id, session_id)
