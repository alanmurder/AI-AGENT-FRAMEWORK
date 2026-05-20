"""wrap_tool_call middleware — routes approved commands to Docker sandbox."""

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command

from harness.sandbox.runner import SandboxRunner
from runtime.context_schema import UserContext


class SandboxMiddleware(AgentMiddleware):
    """Routes command_exec calls to Docker sandbox after security approval.

    After SecurityCheckMiddleware approves a command, this middleware:
    1. Checks if sandbox is available (Docker configured)
    2. Routes to SandboxRunner if available
    3. Falls back to direct execution if Docker unavailable

    MVP: only command_exec is sandboxed. Other tools always run on host.
    """

    def __init__(self, sandbox_runner: SandboxRunner | None = None):
        self.sandbox_runner = sandbox_runner

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command]) -> ToolMessage | Command:
        """Route command_exec to sandbox if available."""
        tool_name = request.tool_call["name"]

        # Only sandbox command_exec
        if tool_name != "command_exec":
            return handler(request)

        if not self.sandbox_runner or not self.sandbox_runner.is_available():
            # No sandbox — fall through to host execution (original handler)
            return handler(request)

        tool_args = request.tool_call.get("args", {})
        command = tool_args.get("command", "")
        timeout = tool_args.get("timeout", 30) or self.sandbox_runner.image and 30

        # Get user context for isolation
        user_id = "default"
        if request.runtime and request.runtime.context:
            user_ctx: UserContext = request.runtime.context
            user_id = user_ctx.user_id

        result = self.sandbox_runner.run_command(
            command=command,
            timeout=timeout or 30,
            network_access=False,
            max_memory="256m",
            user_id=user_id,
        )

        # Format output
        output = result["stdout"]
        if result["stderr"]:
            output += f"\nSTDERR:\n{result['stderr']}"
        if result["exit_code"] != 0:
            output += f"\nExit code: {result['exit_code']}"
        if result["timed_out"]:
            output = f"Command timed out after {timeout}s (sandbox)"
        if not output:
            output = "(no output)"

        output = f"[sandbox] {output}"

        return ToolMessage(content=output, tool_call_id=request.tool_call["id"])