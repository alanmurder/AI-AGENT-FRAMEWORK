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