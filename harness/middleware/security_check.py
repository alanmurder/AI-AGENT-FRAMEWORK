"""wrap_tool_call middleware — L0-L4 security approval for dangerous operations."""

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command

from harness.security.approval import ApprovalChecker
from harness.security.types import ApprovalLevel
from runtime.context_schema import UserContext


class SecurityCheckMiddleware(AgentMiddleware):
    """Checks tool calls against L0-L4 approval levels.

    L0-L1: Always blocks on match (blacklist/patterns).
    L2: Whitelist — blocks if not in safe list, but L3/L4 roles can escalate.
    L3: LLM review — mini_model evaluates safety of borderline operations.
    L4: Human-in-the-loop — blocks pending human approval.
    """

    def __init__(self, approval_checker: ApprovalChecker):
        self.approval_checker = approval_checker

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command]) -> ToolMessage | Command:
        """Run security approval check before executing a tool call."""
        tool_name = request.tool_call["name"]
        tool_args = request.tool_call.get("args", {})
        user_ctx = None

        if request.runtime and request.runtime.context:
            user_ctx = request.runtime.context

        # Only check dangerous tools for security
        if tool_name not in ("command_exec", "file_write", "query_database"):
            return handler(request)

        # Get the content to check
        content_to_check = ""
        if tool_name == "command_exec":
            content_to_check = tool_args.get("command", "")
        elif tool_name == "file_write":
            content_to_check = tool_args.get("content", "")
        elif tool_name == "query_database":
            content_to_check = tool_args.get("sql", "")

        if not content_to_check:
            return handler(request)

        # Run L0-L4 approval chain
        result = self.approval_checker.check(content_to_check, tool_name, user_ctx)

        if result.approved:
            return handler(request)

        # Blocked — return error message to the model
        if result.level == ApprovalLevel.L4:
            return ToolMessage(
                content=f"Operation requires human approval: {result.reason}. "
                        f"Please inform the user that this operation needs manual approval "
                        f"before proceeding.",
                tool_call_id=request.tool_call["id"],
            )

        return ToolMessage(
            content=f"Operation blocked by security policy: {result.reason}. "
                    f"Level: {result.level.value}. Please modify your approach and try again.",
            tool_call_id=request.tool_call["id"],
        )