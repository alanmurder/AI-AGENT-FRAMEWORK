"""Placeholder replacement — store large ToolMessage content in artifact field."""

from dataclasses import dataclass
from collections.abc import Callable
from typing import Sequence

from langchain.agents.middleware.context_editing import ContextEdit
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage


@dataclass
class FileReferenceEdit(ContextEdit):
    """Replace large ToolMessage content with a concise reference, preserving full content in artifact.

    The artifact field is not sent to the model and doesn't count toward token usage,
    so this effectively reduces the visible context size while keeping full data accessible
    for downstream processing or debugging.
    """

    trigger: int = 2000
    keep: int = 3

    def apply(
        self,
        messages: list[AnyMessage],
        *,
        count_tokens: Callable[[Sequence[AnyMessage]], int],
    ) -> None:
        tokens = count_tokens(messages)
        if tokens <= self.trigger:
            return

        candidates = [
            (idx, msg) for idx, msg in enumerate(messages)
            if isinstance(msg, ToolMessage) and not msg.response_metadata.get("context_editing", {}).get("file_referenced")
        ]

        if len(candidates) <= self.keep:
            return

        # Keep the most recent `keep` tool results intact
        to_replace = candidates[: len(candidates) - self.keep]

        for idx, tool_message in to_replace:
            full_content = tool_message.content
            messages[idx] = tool_message.model_copy(update={
                "content": f"[Output saved in artifact. tool_call_id={tool_message.tool_call_id}]",
                "artifact": full_content,
                "response_metadata": {
                    **tool_message.response_metadata,
                    "context_editing": {
                        "file_referenced": True,
                        "strategy": "file_reference",
                    },
                },
            })