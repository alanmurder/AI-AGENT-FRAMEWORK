import json
import os
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from langchain_core.messages import AIMessage

for _proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_proxy_var, None)

from gateway import server
from runtime.context_schema import UserContext, UserRole


class FakeWebSocket:
    def __init__(self, incoming: list[dict[str, str]]):
        self._incoming = [json.dumps(item) for item in incoming]
        self.sent: list[dict] = []
        self.accepted = False
        self.closed_code = None

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        if self._incoming:
            return self._incoming.pop(0)
        raise WebSocketDisconnect()

    async def send_text(self, text: str):
        self.sent.append(json.loads(text))

    async def close(self, code: int | None = None):
        self.closed_code = code


class CapturingSessionPersistence:
    def __init__(self):
        self.records: list[dict] = []

    def write_message(self, user_id, session_id, message, agent_id="", process_events=None):
        if isinstance(message, dict):
            record = dict(message)
        else:
            record = {
                "type": getattr(message, "type", ""),
                "content": getattr(message, "content", ""),
            }
            if getattr(message, "tool_calls", None):
                record["tool_calls"] = [
                    {"id": tc.get("id"), "name": tc.get("name"), "args": tc.get("args")}
                    for tc in message.tool_calls
                ]

        if process_events is not None:
            record["process_events"] = process_events
        record["user_id"] = user_id
        record["session_id"] = session_id
        record["agent_id"] = agent_id
        self.records.append(record)


class FakeAgent:
    def __init__(self, messages):
        self.messages = messages

    def stream(self, *_args, **_kwargs):
        return [{"agent": {"messages": self.messages}}]


def _ctx():
    return UserContext(
        user_id="admin",
        role=UserRole.ADMIN,
        tenant_id="default",
        permissions=[],
        memory_path="",
        session_id="",
        agent_id="",
    )


def _skill(name: str):
    return SimpleNamespace(
        name=name,
        description=f"{name} description",
        category=SimpleNamespace(value="file_manager"),
    )


def _patch_ws_dependencies(monkeypatch, agent, persistence):
    monkeypatch.setattr(server, "authenticate_user", lambda **_kwargs: _ctx())
    monkeypatch.setattr(server, "memory_manager", SimpleNamespace(init_user=lambda _user_id: None))
    monkeypatch.setattr(server, "create_agent_for_user", lambda *_args, **_kwargs: agent)
    monkeypatch.setattr(
        server,
        "skill_manager",
        SimpleNamespace(list_skills_for_role=lambda _role: [_skill("file_manager")]),
    )
    monkeypatch.setattr(server, "session_persistence", persistence)


@pytest.mark.asyncio
async def test_ws_chat_persists_skill_manifest_in_final_process_events(monkeypatch):
    persistence = CapturingSessionPersistence()
    _patch_ws_dependencies(monkeypatch, FakeAgent([AIMessage(content="answer")]), persistence)
    websocket = FakeWebSocket([
        {"token": "valid", "user_id": "admin"},
        {"content": "hello"},
    ])

    await server.ws_chat(websocket)

    ai_records = [record for record in persistence.records if record.get("type") == "ai"]
    assert ai_records[-1]["content"] == "answer"
    assert [event["type"] for event in ai_records[-1]["process_events"]] == [
        "skill_manifest",
        "progress",
    ]


@pytest.mark.asyncio
async def test_ws_chat_strips_skill_use_markers_from_persisted_tool_call_messages(monkeypatch):
    persistence = CapturingSessionPersistence()
    tool_message = AIMessage(
        content='[skill_use name="file_manager" phase="planning" reason="Need files"]',
        tool_calls=[{"id": "tc1", "name": "file_read", "args": {"path": "README.md"}}],
    )
    _patch_ws_dependencies(monkeypatch, FakeAgent([tool_message]), persistence)
    websocket = FakeWebSocket([
        {"token": "valid", "user_id": "admin"},
        {"content": "read file"},
    ])

    await server.ws_chat(websocket)

    tool_ai_records = [
        record for record in persistence.records
        if record.get("type") == "ai" and record.get("tool_calls")
    ]
    assert tool_ai_records
    assert "[skill_use" not in tool_ai_records[0]["content"]
