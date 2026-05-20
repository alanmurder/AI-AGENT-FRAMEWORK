"""Context compressor — creates SummarizationMiddleware and ContextEditingMiddleware."""

from langchain.agents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware.context_editing import ContextEditingMiddleware
from langchain_core.language_models import BaseChatModel

from harness.context.types import ContextConfig
from harness.context.placeholder import FileReferenceEdit
from runtime.config import AgentConfig


def build_context_config(agent_config: AgentConfig) -> ContextConfig:
    """Build a ContextConfig from AgentConfig fields."""
    return ContextConfig(
        compression_threshold=agent_config.compression_threshold,
        flush_threshold=agent_config.flush_threshold,
        max_flush_per_session=agent_config.max_flush_per_session,
        placeholder_threshold=agent_config.placeholder_threshold,
        keep_recent_messages=agent_config.keep_recent_messages,
    )


class ContextCompressor:
    """Creates pre-configured compression and editing middleware instances."""

    def __init__(self, config: ContextConfig, model: BaseChatModel):
        self.config = config
        self.model = model

    def create_summarization_middleware(self) -> SummarizationMiddleware:
        """Create a SummarizationMiddleware that triggers at the configured token threshold."""
        return SummarizationMiddleware(
            model=self.model,
            trigger=("tokens", self.config.compression_threshold),
            keep=("messages", self.config.keep_recent_messages),
        )

    def create_context_editing_middleware(self) -> ContextEditingMiddleware:
        """Create a ContextEditingMiddleware with FileReferenceEdit for large tool outputs."""
        return ContextEditingMiddleware(
            edits=[
                FileReferenceEdit(
                    trigger=self.config.placeholder_threshold,
                    keep=3,
                ),
            ],
        )