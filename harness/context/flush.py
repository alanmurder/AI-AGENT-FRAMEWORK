"""Pre-Flush mechanism — save key info before compression kicks in."""

import asyncio
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.runtime import Runtime

from harness.context.types import ContextConfig
from harness.memory.manager import MemoryManager
from runtime.context_schema import UserContext

_FLUSH_PROMPT = (
    "IMPORTANT: Your conversation context is getting long and will soon be compressed. "
    "Before that happens, please save any critical facts, decisions, or user preferences "
    "you want to preserve. Use the memory_manage tool to write key information to USER.md "
    "and MEMORY.md. After saving, just respond with 'SAVED'."
)


class PreFlushMiddleware(AgentMiddleware):
    """Injects a save-key-info instruction before summarization compresses the context.

    Works as a wrap_model_call middleware: when token count exceeds flush_threshold
    and this session hasn't flushed yet, it:
    1. Appends a flush instruction HumanMessage to the model request
    2. Calls the model to get a save response
    3. If the agent uses tools during flush, the tool results are included
    4. Marks flush as triggered for this session (via Redis)
    5. Returns the original model response (flush round is hidden from the user)

    The flush AI message + tool messages will be part of the conversation history,
    so SummarizationMiddleware will include them when it compresses.
    """

    def __init__(self, memory_manager: MemoryManager, config: ContextConfig):
        self.memory_manager = memory_manager
        self.config = config
        self._flush_triggered_sessions: set[str] = set()

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse | AIMessage],
    ) -> ModelResponse | AIMessage:
        # 1. Check if flush is needed
        runtime = request.runtime
        if runtime is None or runtime.context is None:
            return handler(request)

        user_ctx: UserContext = runtime.context
        session_id = user_ctx.session_id

        # Already flushed this session?
        if session_id in self._flush_triggered_sessions:
            return handler(request)

        # 2. Count tokens
        tokens = count_tokens_approximately(request.messages)
        if tokens < self.config.flush_threshold:
            return handler(request)

        # 3. Inject flush instruction
        flush_msg = HumanMessage(content=_FLUSH_PROMPT, name="system_flush_instruction")
        flush_messages = list(request.messages) + [flush_msg]
        flush_request = request.override(messages=flush_messages)

        # 4. Call model with flush request
        response = handler(flush_request)

        # 5. Mark flush as triggered
        self._flush_triggered_sessions.add(session_id)

        # Also persist to Redis so the flag survives across middleware instances
        try:
            asyncio.get_event_loop().run_until_complete(
                self.memory_manager.short_term.set_flush_triggered(
                    user_ctx.user_id, session_id
                )
            )
        except RuntimeError:
            pass  # No event loop available (sync context) — in-memory flag suffices

        # 6. Return a no-op response so the flush round is invisible to the user
        # The flush AI message and any tool calls are already in the state
        # (LangGraph adds them automatically), so SummarizationMiddleware will see them.
        # We return an empty AIMessage to signal "flush done, no user-visible output".
        return AIMessage(content="", name="NO_REPLY")