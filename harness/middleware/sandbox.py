"""wrap_tool_call middleware - routes approved tool calls to sandbox backends."""

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command

from harness.sandbox.manager import SandboxManager
from harness.sandbox.types import SandboxError, SandboxResult
from runtime.context_schema import UserContext


class SandboxMiddleware(AgentMiddleware):
    """Routes file and execution tools to the configured sandbox after approval.

    After SecurityCheckMiddleware approves a command, this middleware:
    1. Resolves the current UserContext
    2. Routes file/command/Python tools to SandboxManager
    3. Blocks safely when fail-closed sandbox execution is unavailable

    memory_manage remains a platform-memory tool and is not sandboxed.
    """

    SANDBOXED_TOOLS = {"file_read", "file_write", "command_exec", "python_exec"}

    def __init__(self, sandbox_runner: SandboxManager | None = None):
        self.sandbox_runner = sandbox_runner

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command]) -> ToolMessage | Command:
        """Route sandboxed tools to SandboxManager if enabled."""
        tool_name = request.tool_call["name"]

        if tool_name not in self.SANDBOXED_TOOLS:
            return handler(request)

        if not self.sandbox_runner:
            return handler(request)

        if getattr(self.sandbox_runner, "enabled", True) is False:
            return handler(request)

        tool_args = request.tool_call.get("args", {})
        user_ctx = UserContext(user_id="default")
        if request.runtime and request.runtime.context:
            user_ctx = request.runtime.context

        try:
            result = self._run_sandboxed_tool(tool_name, tool_args, user_ctx)
        except SandboxError as e:
            return ToolMessage(content=str(e), tool_call_id=request.tool_call["id"])
        except Exception as e:
            return ToolMessage(content=f"Sandbox error: {e}", tool_call_id=request.tool_call["id"])

        return ToolMessage(content=self._format_result(tool_name, result), tool_call_id=request.tool_call["id"])

    def _run_sandboxed_tool(self, tool_name: str, tool_args: dict, user_ctx: UserContext) -> SandboxResult:
        timeout = tool_args.get("timeout", 30) or 30
        if tool_name == "file_read":
            return self.sandbox_runner.read_file(user_ctx, tool_args.get("path", ""))
        if tool_name == "file_write":
            return self.sandbox_runner.write_file(
                user_ctx,
                tool_args.get("path", ""),
                tool_args.get("content", ""),
            )
        if tool_name == "command_exec":
            return self.sandbox_runner.run_shell(user_ctx, tool_args.get("command", ""), timeout=timeout)
        if tool_name == "python_exec":
            return self.sandbox_runner.run_python(user_ctx, tool_args.get("code", ""), timeout=timeout)
        raise SandboxError(f"Unsupported sandbox tool: {tool_name}")

    @staticmethod
    def _format_result(tool_name: str, result: SandboxResult) -> str:
        output = result.stdout or ""
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}" if output else f"STDERR:\n{result.stderr}"
        if result.exit_code != 0:
            output += f"\nExit code: {result.exit_code}" if output else f"Exit code: {result.exit_code}"
        if result.timed_out:
            output = "Command timed out (sandbox)"
        if not output:
            output = "(no output)"

        if tool_name in ("file_read", "file_write"):
            return output
        return f"[sandbox:{result.backend}] {output}"
