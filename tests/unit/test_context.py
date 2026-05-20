"""Unit tests for Context Management system."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

from harness.context.types import ContextConfig
from harness.context.placeholder import FileReferenceEdit


def test_context_config_defaults():
    cfg = ContextConfig()
    assert cfg.compression_threshold == 4000
    assert cfg.flush_threshold == 60000
    assert cfg.placeholder_threshold == 2000
    assert cfg.keep_recent_messages == 20


def test_file_reference_edit_no_trigger():
    """Below threshold, no edits should be applied."""
    messages = [
        HumanMessage(content="hello"),
        AIMessage(content="hi"),
    ]
    edit = FileReferenceEdit(trigger=5000)
    edit.apply(messages, count_tokens=count_tokens_approximately)
    assert messages[0].content == "hello"


def test_file_reference_edit_replaces_large_tool_output():
    """Large ToolMessage should be replaced with reference when total tokens exceed trigger."""
    # Need multiple ToolMessages so keep=1 logic can replace older ones
    large_content = "x" * 8000
    filler = "padding " * 200
    messages = [
        HumanMessage(content=filler),
        AIMessage(content="", tool_calls=[
            {"id": "tc1", "name": "file_read", "args": {"path": "/big"}},
            {"id": "tc2", "name": "cmd", "args": {"cmd": "ls"}},
        ]),
        ToolMessage(content=large_content, tool_call_id="tc1", name="file_read"),
        ToolMessage(content="small", tool_call_id="tc2", name="cmd"),
    ]

    assert count_tokens_approximately(messages) > 2000

    edit = FileReferenceEdit(trigger=2000, keep=1)
    edit.apply(messages, count_tokens=count_tokens_approximately)

    # tc1 (older) should be replaced, tc2 (most recent) kept
    assert "Output saved in artifact" in messages[2].content
    assert messages[2].artifact == large_content
    assert messages[3].content == "small"


def test_file_reference_edit_keeps_recent():
    """Recent tool outputs should not be replaced."""
    filler = "padding content " * 200  # push tokens above threshold
    messages = [
        HumanMessage(content=filler),
        AIMessage(content="", tool_calls=[{"id": "tc1", "name": "cmd", "args": {}}, {"id": "tc2", "name": "cmd", "args": {}}]),
        ToolMessage(content="x" * 5000, tool_call_id="tc1", name="cmd"),
        ToolMessage(content="small result", tool_call_id="tc2", name="cmd"),
    ]

    assert count_tokens_approximately(messages) > 2000

    edit = FileReferenceEdit(trigger=2000, keep=1)
    edit.apply(messages, count_tokens=count_tokens_approximately)

    # tc1 (older) should be replaced, tc2 (most recent, kept) should remain
    assert "Output saved in artifact" in messages[2].content
    assert messages[3].content == "small result"