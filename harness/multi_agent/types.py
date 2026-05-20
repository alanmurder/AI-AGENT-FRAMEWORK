"""SubAgent type definitions — roles, configs, results."""

from enum import Enum

from pydantic import BaseModel


class SubAgentRole(str, Enum):
    PLANNER = "planner"
    GENERATOR = "generator"
    EVALUATOR = "evaluator"
    WORKER = "worker"


class SubAgentConfig(BaseModel):
    role: SubAgentRole = SubAgentRole.WORKER
    system_prompt: str = ""
    tools: list[str] = []  # empty = read-only (file_read, web_search, query_database, memory_manage)
    max_depth: int = 1
    timeout: int = 120
    model_type: str = "mini"  # "primary" | "mini"


class SubAgentResult(BaseModel):
    task_id: str
    role: SubAgentRole
    content: str
    success: bool
    metadata: dict = {}
    error: str | None = None


# Default tool sets by access level
READONLY_TOOLS = ["file_read", "web_search", "query_database", "memory_manage"]
FULL_TOOLS = ["file_read", "file_write", "command_exec", "web_search", "query_database", "send_notification", "memory_manage"]

# Tools available to each SubAgent role
ROLE_TOOLS: dict[SubAgentRole, list[str]] = {
    SubAgentRole.PLANNER: READONLY_TOOLS,
    SubAgentRole.GENERATOR: ["file_read", "file_write", "web_search", "memory_manage"],
    SubAgentRole.EVALUATOR: READONLY_TOOLS,
    SubAgentRole.WORKER: FULL_TOOLS,
}
