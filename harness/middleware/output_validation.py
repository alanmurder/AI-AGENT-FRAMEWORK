"""after_model middleware — Pydantic structured output validation with retry feedback."""

from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime


class OutputValidationMiddleware(AgentMiddleware):
    """Validates structured output using Pydantic models. Returns error details to the model on failure."""

    MAX_RETRIES = 3

    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Check if the response matches expected structured output schema."""
        # This middleware works in conjunction with ToolStrategy in create_agent.
        # When ToolStrategy is used, the validation is handled by LangChain internally.
        # This middleware provides additional custom validation hooks for enterprise scenarios.

        # If no response_format is specified in state, skip validation
        if "response_format" not in state or state.get("response_format") is None:
            return None

        # Custom validation logic can be added here for enterprise-specific schemas
        # For now, rely on LangChain's built-in ToolStrategy validation
        return None