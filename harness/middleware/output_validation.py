"""after_model middleware — validates structured output and feeds errors back to the model for retry."""

import json
import structlog
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.runtime import Runtime

logger = structlog.get_logger()

_RETRY_COUNT_KEY = "__output_validation_retries__"

_VALIDATION_FEEDBACK_TEMPLATE = (
    "Your previous response failed output validation. "
    "Please correct it and try again.\n\n"
    "Validation errors:\n{errors}\n\n"
    "Expected format: {expected}\n\n"
    "Please respond with a valid output that matches the expected format."
)


class OutputValidationMiddleware(AgentMiddleware):
    """Validates structured LLM output and feeds errors back to the model for retry.

    When response_format is specified in state, each AI response is validated
    against the expected schema. On failure, a ToolMessage is injected with
    the validation errors so the model can self-correct.

    Supports:
    - Pydantic model validation (response_format is a BaseModel subclass)
    - JSON schema validation (response_format is a dict/json schema)
    - JSON parse + basic field check
    """

    MAX_RETRIES = 3

    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        response_format = state.get("response_format")
        if response_format is None:
            return None

        messages = state.get("messages", [])
        if not messages:
            return None

        # Get the last AI message
        last_ai = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and not _is_retry_feedback(msg):
                last_ai = msg
                break

        if last_ai is None:
            return None

        content = last_ai.content
        if not isinstance(content, str) or not content.strip():
            return None

        # Count retries so far
        retry_count = self._get_retry_count(state)

        # Attempt validation
        errors = self._validate(content, response_format)

        if not errors:
            # Passed — reset retry counter
            return {_RETRY_COUNT_KEY: 0}

        # Failed validation
        logger.info("output_validation_failed",
            retry_count=retry_count, errors=errors[:200],
            content_preview=content[:200])

        if retry_count >= self.MAX_RETRIES:
            logger.warning("output_validation_max_retries",
                retry_count=retry_count, content_preview=content[:200])
            return {_RETRY_COUNT_KEY: 0}

        # Build error feedback
        expected_desc = self._describe_format(response_format)
        feedback = _VALIDATION_FEEDBACK_TEMPLATE.format(
            errors="\n".join(f"- {e}" for e in errors),
            expected=expected_desc,
        )

        # Return feedback as ToolMessage — the model sees it as tool output
        # and will retry. We attach a marker name for retry tracking.
        new_retry = retry_count + 1
        return {
            "messages": [
                ToolMessage(
                    content=feedback,
                    tool_call_id="output_validation",
                    name="output_validator",
                ),
            ],
            _RETRY_COUNT_KEY: new_retry,
        }

    # ── internal ──

    def _validate(self, content: str, response_format: Any) -> list[str]:
        """Validate content against the response_format. Returns list of error messages."""
        errors = []

        # Strategy 1: Pydantic model
        if _is_pydantic_model(response_format):
            return self._validate_pydantic(content, response_format)

        # Strategy 2: JSON Schema dict
        if isinstance(response_format, dict):
            return self._validate_json_schema(content, response_format)

        # Strategy 3: Try JSON parse + basic check
        return self._validate_json_basic(content)

    @staticmethod
    def _validate_pydantic(content: str, model_class) -> list[str]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return [f"Invalid JSON: {e}"]

        try:
            model_class.model_validate(data)
        except Exception as e:
            return [str(e)]

        return []

    @staticmethod
    def _validate_json_schema(content: str, schema: dict) -> list[str]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return [f"Invalid JSON: {e}"]

        errors = []
        if "properties" in schema:
            for field, props in schema["properties"].items():
                if field not in data:
                    if field in schema.get("required", []):
                        errors.append(f"Missing required field: '{field}'")
                elif "type" in props:
                    expected_type = props["type"]
                    actual_type = _json_type(data[field])
                    if actual_type != expected_type:
                        errors.append(
                            f"Field '{field}': expected {expected_type}, got {actual_type}"
                        )
        return errors

    @staticmethod
    def _validate_json_basic(content: str) -> list[str]:
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return [f"Invalid JSON: {e}"]
        return []

    @staticmethod
    def _get_retry_count(state: AgentState) -> int:
        return state.get(_RETRY_COUNT_KEY, 0)

    @staticmethod
    def _describe_format(response_format: Any) -> str:
        if _is_pydantic_model(response_format):
            fields = []
            for name, field in response_format.model_fields.items():
                fields.append(f"  {name}: {field.annotation.__name__ if hasattr(field.annotation, '__name__') else str(field.annotation)}")
            return f"JSON object with fields:\n" + "\n".join(fields)
        if isinstance(response_format, dict):
            return f"JSON object with schema: {json.dumps(response_format, indent=2)}"
        return "valid JSON"


def _is_pydantic_model(obj: Any) -> bool:
    try:
        from pydantic import BaseModel
        return isinstance(obj, type) and issubclass(obj, BaseModel)
    except TypeError:
        return False


def _is_retry_feedback(msg: AIMessage) -> bool:
    """Check if an AIMessage is a retry attempt marker."""
    return bool(msg.content and _VALIDATION_FEEDBACK_TEMPLATE[:50] in str(msg.content))


def _json_type(value: Any) -> str:
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"
