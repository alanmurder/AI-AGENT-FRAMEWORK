"""JSONL session persistence — crash-safe per-session message logging."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, BaseMessage


class SessionPersistence:
    """Writes each message to a JSONL file as it arrives, ensuring crash safety.

    JSONL format: each line is a JSON object with metadata + message content.
    File path: {base_dir}/sessions/{user_id}/{session_id}.jsonl
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir / "sessions"

    def _session_path(self, user_id: str, session_id: str) -> Path:
        d = self.base_dir / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{session_id}.jsonl"

    def write_message(self, user_id: str, session_id: str, msg: BaseMessage, agent_id: str = "") -> None:
        """Append a message to the session JSONL file."""
        path = self._session_path(user_id, session_id)

        record = {
            "timestamp": datetime.now().isoformat(),
            "type": msg.type,
            "content": msg.content if isinstance(msg.content, str) else str(msg.content),
            "agent_id": agent_id,
        }

        if isinstance(msg, AIMessage):
            record["tool_calls"] = [
                {"id": tc.get("id"), "name": tc.get("name"), "args": tc.get("args")}
                for tc in msg.tool_calls
            ]
        elif isinstance(msg, ToolMessage):
            record["tool_call_id"] = msg.tool_call_id
            record["name"] = msg.name

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_session(self, user_id: str, session_id: str) -> list[dict]:
        """Load all messages from a session JSONL file for replay/recovery."""
        path = self._session_path(user_id, session_id)
        if not path.exists():
            return []

        messages = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
        return messages

    def list_sessions(self, user_id: str) -> list[dict]:
        """List all session IDs for a user, with metadata from first message."""
        d = self.base_dir / user_id
        if not d.exists():
            return []
        results = []
        for p in sorted(d.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
            info = {"session_id": p.stem, "agent_id": ""}
            try:
                first_line = p.open(encoding="utf-8").readline()
                if first_line:
                    record = json.loads(first_line)
                    info["agent_id"] = record.get("agent_id", "")
            except Exception:
                pass
            results.append(info)
        return results