"""Unit tests for JSONL Session persistence."""

from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from gateway.session import SessionPersistence


def test_write_and_load(tmp_path):
    sp = SessionPersistence(tmp_path)
    sp.write_message("user1", "sess-001", HumanMessage(content="Hello"))
    sp.write_message("user1", "sess-001", AIMessage(content="Hi there!"))

    msgs = sp.load_session("user1", "sess-001")
    assert len(msgs) == 2
    assert msgs[0]["type"] == "human"
    assert msgs[0]["content"] == "Hello"
    assert msgs[1]["type"] == "ai"


def test_tool_message_persistence(tmp_path):
    sp = SessionPersistence(tmp_path)
    sp.write_message("user1", "sess-002", AIMessage(
        content="", tool_calls=[{"id": "tc1", "name": "file_read", "args": {"path": "/tmp"}}]
    ))
    sp.write_message("user1", "sess-002", ToolMessage(
        content="file contents", tool_call_id="tc1", name="file_read"
    ))

    msgs = sp.load_session("user1", "sess-002")
    assert msgs[0]["tool_calls"][0]["name"] == "file_read"
    assert msgs[1]["tool_call_id"] == "tc1"


def test_list_sessions(tmp_path):
    sp = SessionPersistence(tmp_path)
    sp.write_message("user1", "sess-a", HumanMessage(content="msg"))
    sp.write_message("user1", "sess-b", HumanMessage(content="msg"))

    sessions = sp.list_sessions("user1")
    session_ids = [s["session_id"] for s in sessions]
    assert "sess-a" in session_ids
    assert "sess-b" in session_ids
    # Verify agent_id is recorded
    for s in sessions:
        assert "agent_id" in s


def test_write_message_with_agent_id(tmp_path):
    sp = SessionPersistence(tmp_path)
    sp.write_message("user1", "sess-expert", HumanMessage(content="help"), agent_id="equipment_monitor")
    sp.write_message("user1", "sess-expert", AIMessage(content="I can help"), agent_id="equipment_monitor")

    msgs = sp.load_session("user1", "sess-expert")
    assert len(msgs) == 2
    assert msgs[0]["agent_id"] == "equipment_monitor"
    assert msgs[1]["agent_id"] == "equipment_monitor"
    assert msgs[0]["content"] == "help"


def test_load_nonexistent_session(tmp_path):
    sp = SessionPersistence(tmp_path)
    msgs = sp.load_session("unknown", "nonexistent")
    assert msgs == []


def test_ai_message_persists_process_events(tmp_path):
    sp = SessionPersistence(tmp_path)
    process_events = [
        {
            "type": "skill_use",
            "name": "knowledge_search",
            "phase": "answering",
            "reason": "Need docs",
            "session_id": "sess-process",
        }
    ]

    sp.write_message(
        "user1",
        "sess-process",
        AIMessage(content="Answer"),
        process_events=process_events,
    )

    msgs = sp.load_session("user1", "sess-process")
    assert msgs[0]["process_events"] == process_events


def test_dict_message_persistence_supports_process_events_and_tool_calls(tmp_path):
    sp = SessionPersistence(tmp_path)
    process_events = [{"type": "tool_call", "name": "file_read", "args": {"path": "a.txt"}}]

    sp.write_message(
        "user1",
        "sess-dict",
        {
            "type": "ai",
            "content": "Answer from dict",
            "tool_calls": [{"id": "tc1", "name": "file_read", "args": {"path": "a.txt"}}],
        },
        agent_id="agent-1",
        process_events=process_events,
    )

    msgs = sp.load_session("user1", "sess-dict")
    assert msgs[0]["type"] == "ai"
    assert msgs[0]["content"] == "Answer from dict"
    assert msgs[0]["agent_id"] == "agent-1"
    assert msgs[0]["tool_calls"][0]["name"] == "file_read"
    assert msgs[0]["process_events"] == process_events
