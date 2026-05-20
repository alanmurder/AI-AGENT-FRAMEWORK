"""Seven base tools for the AI Agent Platform."""

import os
import subprocess
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from langchain.tools import tool


@tool
def file_read(path: str) -> str:
    """Read file content. Use this to read SKILL.md files, configuration files, data files, etc."""
    try:
        p = Path(path)
        if not p.exists():
            return f"Error: File not found: {path}"
        content = p.read_text(encoding="utf-8")
        max_chars = 50000
        if len(content) > max_chars:
            return content[:max_chars] + f"\n... [truncated, total {len(content)} chars]"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


@tool
def file_write(path: str, content: str) -> str:
    """Write content to a file. Use this to write reports, configurations, memory files, etc."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool
def command_exec(command: str, timeout: int = 30) -> str:
    """Execute a shell command. Use this to run scripts, query databases, and perform system operations.
    WARNING: Dangerous commands are subject to security approval (L0-L4 levels)."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
        max_chars = 10000
        if len(output) > max_chars:
            return output[:max_chars] + f"\n... [truncated, total {len(output)} chars]"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Error executing command: {e}"


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information using DuckDuckGo. Use this to look up documentation, research topics, find current data, etc."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })

        if not results:
            return f"No results found for '{query}'"

        output = f"Search results for '{query}':\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}\n"
        return output
    except Exception as e:
        return f"Error searching web: {e}"


@tool
def query_database(sql: str, database: str = "default") -> str:
    """Query a database using SQL. Returns results as JSON.
    Only SELECT queries are allowed for safety. WARNING: Subject to security approval.
    database: name of the database file (without extension) in the data directory."""
    try:
        # MVP: Use local SQLite database files
        from runtime.config import AgentConfig
        config = AgentConfig()
        data_dir = config.get_memory_base_dir() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        db_path = data_dir / f"{database}.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Safety: only allow SELECT
        stripped = sql.strip().upper()
        if not stripped.startswith("SELECT"):
            return "Error: Only SELECT queries are allowed."

        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        result = {
            "columns": columns,
            "rows": [dict(row) for row in rows],
            "row_count": len(rows),
        }
        conn.close()

        if len(rows) == 0:
            return f"Query returned 0 rows. Columns: {columns}"

        output = json.dumps(result, ensure_ascii=False, default=str)
        max_chars = 10000
        if len(output) > max_chars:
            return output[:max_chars] + f"\n... [truncated, total {len(rows)} rows]"
        return output
    except Exception as e:
        return f"Error querying database: {e}"


@tool
def send_notification(message: str, channel: str = "web", recipient: str = "") -> str:
    """Send a notification message to a user or channel.
    Use this for alerts, reminders, reports, etc.
    channel: web, dingtalk, feishu, or wecom (only web is implemented in MVP).
    recipient: target user ID or group name."""
    try:
        from runtime.config import AgentConfig
        config = AgentConfig()
        notify_dir = config.get_memory_base_dir() / "notifications"
        notify_dir.mkdir(parents=True, exist_ok=True)

        # Write notification log
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        log_file = notify_dir / f"{timestamp}_{channel}_{recipient or 'broadcast'}.json"
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "channel": channel,
            "recipient": recipient,
            "message": message,
            "status": "sent",
        }
        log_file.write_text(json.dumps(log_data, ensure_ascii=False), encoding="utf-8")

        # Channel-specific handling
        if channel == "dingtalk":
            return f"Notification logged (DingTalk integration pending Phase 2): {message[:100]}"
        elif channel == "feishu":
            return f"Notification logged (Feishu integration pending Phase 2): {message[:100]}"
        elif channel == "wecom":
            return f"Notification logged (WeCom integration pending Phase 2): {message[:100]}"
        else:
            # Web channel — notification is logged and will be pushed via WebSocket
            return f"Notification sent via {channel} to '{recipient or 'all'}': {message[:100]}"
    except Exception as e:
        return f"Error sending notification: {e}"


@tool
def memory_manage(action: str, content: str = "", file: str = "", user_id: str = "", base_dir: str = "") -> str:
    """Manage agent memory files. Actions: read, write, append, search.
    Files: SOUL.md, USER.md, MEMORY.md, or daily log paths.
    base_dir: root memory directory (defaults to configured path)."""
    try:
        if base_dir:
            resolved_base = Path(base_dir).expanduser()
        else:
            from runtime.config import AgentConfig
            cfg = AgentConfig()
            resolved_base = cfg.get_memory_base_dir()

        from harness.memory.manager import MemoryManager
        from harness.memory.types import MemoryFile

        mem_manager = MemoryManager(AgentConfig(memory_base_dir=str(resolved_base)))

        effective_user = user_id or "default"

        if action == "read":
            try:
                mem_file = MemoryFile(file)
            except ValueError:
                user_dir = resolved_base / "users" / effective_user
                target = user_dir / file
                if not target.exists():
                    return f"Error: {file} not found for user {effective_user}"
                return target.read_text(encoding="utf-8")
            return mem_manager.long_term.read_file(effective_user, mem_file)

        elif action == "write":
            try:
                mem_file = MemoryFile(file)
                mem_manager.long_term.write_file(effective_user, mem_file, content)
                return f"Written to {file} for user {effective_user}"
            except ValueError:
                user_dir = resolved_base / "users" / effective_user
                target = user_dir / file
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return f"Written to {file} for user {effective_user}"

        elif action == "append":
            try:
                mem_file = MemoryFile(file)
                mem_manager.long_term.append_file(effective_user, mem_file, content)
                return f"Appended to {file} for user {effective_user}"
            except ValueError:
                user_dir = resolved_base / "users" / effective_user
                target = user_dir / file
                target.parent.mkdir(parents=True, exist_ok=True)
                existing = target.read_text(encoding="utf-8") if target.exists() else ""
                target.write_text(existing + "\n" + content, encoding="utf-8")
                return f"Appended to {file} for user {effective_user}"

        elif action == "list":
            user_dir = resolved_base / "users" / effective_user
            if not user_dir.exists():
                return f"No memory directory for user {effective_user}"
            files = [f.name for f in user_dir.iterdir() if f.is_file()]
            return json.dumps(files)

        else:
            return f"Unknown action: {action}. Use read, write, append, or list."
    except Exception as e:
        return f"Error managing memory: {e}"


@tool
def spawn_subagent(role: str, task: str, system_prompt: str = "", expert_id: str = "") -> str:
    """Spawn a sub-agent to handle a specific task. Available for admin/manager roles only.
    Roles: planner, generator, evaluator, worker. Returns the sub-agent's result text.
    expert_id: if specified, loads expert AgentProfile and injects SOUL.md as system prompt.
    When expert_id is set and system_prompt is empty → uses SOUL.md.
    When expert_id is set and system_prompt is non-empty → SOUL.md prefix + system_prompt as task.
    Use this for complex tasks that benefit from an independent agent with its own context."""
    try:
        from runtime.config import AgentConfig
        from harness.multi_agent.types import SubAgentConfig, SubAgentRole
        from harness.multi_agent.subagent import SubAgentRunner
        from harness.memory.manager import MemoryManager
        from harness.skill.manager import SkillManager
        from harness.security.approval import ApprovalChecker

        config = AgentConfig()
        mm = MemoryManager(config)
        sm = SkillManager(config)
        ac = ApprovalChecker()
        runner = SubAgentRunner(config, mm, sm, ac)

        if expert_id:
            from harness.expert.registry import AgentRegistry
            from pathlib import Path
            registry = AgentRegistry()
            root = Path(config.project_root)
            registry.scan_profiles(root / "agents")
            profile = registry.get(expert_id)
            if not profile:
                return f"Error: Expert agent '{expert_id}' not found"
            soul_content = registry.load_soul_content(expert_id, root)
            effective_prompt = soul_content if not system_prompt else f"{soul_content}\n\nTask: {system_prompt}"
            sub_config = SubAgentConfig(role=SubAgentRole.WORKER, system_prompt=effective_prompt)
        else:
            role_map = {r.value: r for r in SubAgentRole}
            sub_role = role_map.get(role, SubAgentRole.WORKER)
            sub_config = SubAgentConfig(role=sub_role, system_prompt=system_prompt)

        from runtime.context_schema import UserContext, UserRole
        ctx = UserContext(user_id="system", role=UserRole.ADMIN, session_id=f"spawn-{uuid.uuid4().hex[:8]}")

        result = runner.spawn(sub_config, task, ctx)
        if result.success:
            return result.content
        else:
            return f"Sub-agent failed: {result.error}"
    except Exception as e:
        return f"Error spawning sub-agent: {e}"


@tool
def delegate_task(task_description: str, role_prompt: str, context: str = "", assignee: str = "", dependencies: list[str] = []) -> str:
    """Delegate a sub-task to a team member or publish to TaskBoard. Captain tool only.
    task_description: what the member should do
    role_prompt: dynamic role prompt to assign to the member
    assignee: specific member ID (empty = publish to TaskBoard for claiming)
    dependencies: task_ids this task depends on (must complete first)."""
    try:
        from runtime.config import AgentConfig
        from harness.team.task_board import TaskBoardManager
        config = AgentConfig()
        board = TaskBoardManager(config)
        task_id = board.create_task(
            board_id="team-default",
            description=task_description,
            role_prompt=role_prompt,
            context=context,
            assignee=assignee,
            dependencies=dependencies,
        )
        return f"Task {task_id} created. Status: pending. Assignee: {assignee or 'auto-claim'}"
    except Exception as e:
        return f"Error delegating task: {e}"


@tool
def read_task_board() -> str:
    """Read the shared TaskBoard — view all sub-task statuses and completed results.
    Available for both captain and team members."""
    try:
        from runtime.config import AgentConfig
        from harness.team.task_board import TaskBoardManager
        config = AgentConfig()
        board = TaskBoardManager(config)
        tasks = board.list_tasks("team-default")
        if not tasks:
            return "TaskBoard is empty — no tasks pending."
        lines = ["TaskBoard:"]
        for t in tasks:
            status_icon = "+" if t.status == "completed" else "-" if t.status == "running" else "o" if t.status == "pending" else "x"
            lines.append(f"  {status_icon} [{t.task_id}] {t.description[:60]} (status={t.status}, assignee={t.assignee or 'none'})")
            if t.result:
                lines.append(f"    Result: {t.result[:100]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading task board: {e}"


@tool
def collect_results() -> str:
    """Collect all completed sub-task results from the TaskBoard. Captain tool only.
    Returns a summary of all completed tasks for final response."""
    try:
        from runtime.config import AgentConfig
        from harness.team.task_board import TaskBoardManager
        config = AgentConfig()
        board = TaskBoardManager(config)
        tasks = board.list_tasks("team-default")
        completed = [t for t in tasks if t.status == "completed"]
        if not completed:
            return "No completed tasks yet."
        lines = ["Completed Task Results:"]
        for t in completed:
            lines.append(f"--- [{t.task_id}] {t.description} ---")
            lines.append(t.result)
        return "\n".join(lines)
    except Exception as e:
        return f"Error collecting results: {e}"


ALL_TOOLS = [file_read, file_write, command_exec, web_search, query_database, send_notification, memory_manage, spawn_subagent]
CAPTAIN_TOOLS = [file_read, file_write, command_exec, web_search, query_database, send_notification, memory_manage, spawn_subagent, delegate_task, read_task_board, collect_results]
MEMBER_TOOLS = [file_read, file_write, command_exec, web_search, query_database, send_notification, memory_manage, read_task_board]
BASE_TOOLS = [file_read, file_write, command_exec, web_search, query_database, send_notification, memory_manage]