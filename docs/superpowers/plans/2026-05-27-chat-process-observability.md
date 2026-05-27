# Chat Process Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a unified chat process event stream that shows loaded Skills, explicit Skill-use declarations, public progress updates, and tool calls in the UI, with matching backend logs.

**Architecture:** Backend code creates normalized process events from session Skill metadata, model-emitted Skill-use markers, progress stages, and tool calls. The WebSocket endpoint streams these events alongside answer chunks and persists them on the final AI message for replay. The frontend stores session Skills and per-turn process events, then renders a compact timeline for live and historical answers.

**Tech Stack:** Python 3.11, FastAPI WebSocket, LangChain/LangGraph agent stream updates, structlog, JSONL session persistence, React 18, TypeScript, Zustand, Ant Design, Vitest, pytest.

---

## File Structure

- Create `harness/observability/__init__.py`
- Create `harness/observability/chat_process.py`
  - Owns process event construction, Skill manifest serialization, Skill-use marker parsing, log-safe truncation, and session Skill filtering helpers.
- Modify `gateway/session.py`
  - Allows optional `process_events` on persisted records and supports dict records used by WebSocket persistence.
- Modify `gateway/server.py`
  - Sends `skill_manifest`, `progress`, `skill_use`, enriched `tool_call`, `chunk`, and `done` events in order. Logs each process event with `structlog`.
- Modify `runtime/agent.py`
  - Appends the public Skill-use marker protocol to the generic Agent system prompt.
- Modify `harness/expert/agent_factory.py`
  - Appends the same public Skill-use marker protocol to expert Agent prompts.
- Modify `web/src/types/chat.ts`
  - Adds Skill summaries, process event types, and enriched stream event types.
- Modify `web/src/store/chatStore.ts`
  - Stores `sessionSkills`, `activeProcessEvents`, and message-level `process_events`.
- Modify `web/src/hooks/useAgentChat.ts`
  - Starts a user turn through the chat store so each streamed answer gets a fresh process timeline seeded with loaded Skills.
- Create `web/src/components/ProcessTimeline.tsx`
  - Renders a compact, collapsible process timeline.
- Modify `web/src/components/StreamOutput.tsx`
  - Renders the active process timeline above streaming content.
- Modify `web/src/components/ChatBubble.tsx`
  - Renders persisted process timelines for historical AI messages.
- Modify `web/src/pages/ChatPage.tsx`
  - Stops rendering active tool calls separately because tool calls become timeline events.
- Create `tests/unit/test_chat_process.py`
  - Tests backend process event helpers.
- Modify `tests/unit/test_session.py`
  - Tests JSONL persistence of `process_events` and dict records.
- Create `web/src/store/chatStore.test.ts`
  - Tests stream event handling and per-turn process event persistence.
- Create `web/src/components/ProcessTimeline.test.tsx`
  - Tests timeline summary and expanded details.

---

### Task 1: Backend Process Event Helpers

**Files:**
- Create: `harness/observability/__init__.py`
- Create: `harness/observability/chat_process.py`
- Test: `tests/unit/test_chat_process.py`

- [ ] **Step 1: Write failing backend helper tests**

Create `tests/unit/test_chat_process.py`:

```python
from types import SimpleNamespace

from runtime.context_schema import UserContext, UserRole


def _skill(name: str, description: str = "Skill description", category: str = "file_manager"):
    return SimpleNamespace(
        name=name,
        description=description,
        category=SimpleNamespace(value=category),
    )


def _ctx(role: UserRole = UserRole.OPERATOR) -> UserContext:
    return UserContext(
        user_id="u1",
        role=role,
        tenant_id="default",
        permissions=[],
        memory_path="",
        session_id="sess-1",
        agent_id="agent-1",
    )


def test_build_skill_manifest_event_serializes_role_filtered_skills():
    from harness.observability.chat_process import build_skill_manifest_event

    event = build_skill_manifest_event(
        skills=[_skill("file_manager", "Manage files"), _skill("knowledge_search", "Search docs", "knowledge_search")],
        user_ctx=_ctx(),
        agent_id="agent-1",
    )

    assert event == {
        "type": "skill_manifest",
        "skills": [
            {"name": "file_manager", "description": "Manage files", "category": "file_manager"},
            {"name": "knowledge_search", "description": "Search docs", "category": "knowledge_search"},
        ],
        "role": "operator",
        "session_id": "sess-1",
        "agent_id": "agent-1",
    }


def test_get_session_skill_infos_filters_expert_profile_skill_names():
    from harness.observability.chat_process import get_session_skill_infos

    class SkillManagerStub:
        def list_skills_for_role(self, role):
            assert role == UserRole.OPERATOR
            return [_skill("file_manager"), _skill("knowledge_search"), _skill("report_generator")]

    profile = SimpleNamespace(skills=["knowledge_search", "missing_skill"])

    skills = get_session_skill_infos(SkillManagerStub(), _ctx(), profile)

    assert [skill.name for skill in skills] == ["knowledge_search"]


def test_extract_skill_use_events_strips_known_marker_from_visible_content():
    from harness.observability.chat_process import extract_skill_use_events

    visible, events, ignored = extract_skill_use_events(
        'Before [skill_use name="knowledge_search" phase="answering" reason="Need product docs"] after',
        available_skill_names={"knowledge_search"},
        session_id="sess-1",
        agent_id="agent-1",
    )

    assert visible == "Before  after"
    assert ignored == []
    assert events == [
        {
            "type": "skill_use",
            "name": "knowledge_search",
            "phase": "answering",
            "reason": "Need product docs",
            "session_id": "sess-1",
            "agent_id": "agent-1",
        }
    ]


def test_extract_skill_use_events_logs_unknown_skill_without_ui_event():
    from harness.observability.chat_process import extract_skill_use_events

    visible, events, ignored = extract_skill_use_events(
        'Start [skill_use name="admin_only" phase="planning" reason="Need it"] end',
        available_skill_names={"file_manager"},
        session_id="sess-1",
        agent_id="agent-1",
    )

    assert visible == "Start  end"
    assert events == []
    assert ignored == [{"name": "admin_only", "phase": "planning", "reason": "Need it"}]


def test_extract_skill_use_events_keeps_malformed_marker_visible():
    from harness.observability.chat_process import extract_skill_use_events

    visible, events, ignored = extract_skill_use_events(
        'Keep [skill_use name="knowledge_search" phase=answering] text',
        available_skill_names={"knowledge_search"},
        session_id="sess-1",
        agent_id="agent-1",
    )

    assert visible == 'Keep [skill_use name="knowledge_search" phase=answering] text'
    assert events == []
    assert ignored == []


def test_truncate_for_log_limits_nested_values():
    from harness.observability.chat_process import truncate_for_log

    value = {"args": {"query": "x" * 700}, "items": ["y" * 700]}

    truncated = truncate_for_log(value, max_length=20)

    assert truncated["args"]["query"] == "x" * 20 + "...<truncated>"
    assert truncated["items"][0] == "y" * 20 + "...<truncated>"
```

- [ ] **Step 2: Run helper tests and verify they fail**

Run:

```bash
pytest tests/unit/test_chat_process.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'harness.observability'`.

- [ ] **Step 3: Implement process event helpers**

Create `harness/observability/__init__.py`:

```python
"""Observability helpers for public runtime events."""
```

Create `harness/observability/chat_process.py`:

```python
"""Helpers for public chat process events.

These events are safe, user-visible process summaries. They must not expose
private model chain-of-thought.
"""

from __future__ import annotations

import re
from typing import Any

from runtime.context_schema import UserContext

SKILL_USE_PROTOCOL_INSTRUCTION = (
    'When you decide to use one of the available Skills, first emit a concise public process marker '
    'exactly in this form: [skill_use name="skill_name" phase="planning|answering|verification" '
    'reason="short public reason"]. Do not include private reasoning in the marker or in the answer.'
)

_SKILL_USE_RE = re.compile(r"\[skill_use\s+(?P<attrs>[^\]]+)\]")
_ATTR_RE = re.compile(r'(?P<key>[A-Za-z_][A-Za-z0-9_]*)="(?P<value>[^"]*)"')


def _skill_category_value(skill: Any) -> str:
    category = getattr(skill, "category", "")
    return getattr(category, "value", category) or ""


def skill_info_to_wire(skill: Any) -> dict[str, str]:
    """Serialize a SkillInfo-like object for WebSocket transport."""
    return {
        "name": getattr(skill, "name", ""),
        "description": getattr(skill, "description", ""),
        "category": _skill_category_value(skill),
    }


def get_session_skill_infos(skill_manager: Any, user_ctx: UserContext, profile: Any | None = None) -> list[Any]:
    """Return the Skills that are available to the current internal Agent session."""
    skills = list(skill_manager.list_skills_for_role(user_ctx.role))
    profile_skill_names = getattr(profile, "skills", None) if profile is not None else None
    if profile_skill_names is not None:
        allowed_names = set(profile_skill_names)
        skills = [skill for skill in skills if getattr(skill, "name", "") in allowed_names]
    return skills


def build_skill_manifest_event(skills: list[Any], user_ctx: UserContext, agent_id: str = "") -> dict[str, Any]:
    """Build the session-level Skill manifest event."""
    return {
        "type": "skill_manifest",
        "skills": [skill_info_to_wire(skill) for skill in skills],
        "role": user_ctx.role.value,
        "session_id": user_ctx.session_id,
        "agent_id": agent_id,
    }


def build_progress_event(stage: str, content: str, user_ctx: UserContext, agent_id: str = "") -> dict[str, Any]:
    """Build a public progress event."""
    return {
        "type": "progress",
        "stage": stage,
        "content": content,
        "session_id": user_ctx.session_id,
        "agent_id": agent_id,
    }


def build_tool_call_event(tool_call: dict[str, Any], user_ctx: UserContext, agent_id: str = "") -> dict[str, Any]:
    """Build a normalized tool-call process event."""
    return {
        "type": "tool_call",
        "id": tool_call.get("id") or "",
        "name": tool_call.get("name", ""),
        "args": tool_call.get("args", {}),
        "session_id": user_ctx.session_id,
        "agent_id": agent_id,
    }


def _parse_attrs(raw_attrs: str) -> dict[str, str] | None:
    attrs = {match.group("key"): match.group("value") for match in _ATTR_RE.finditer(raw_attrs)}
    reconstructed = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    if reconstructed != raw_attrs.strip():
        return None
    if "name" not in attrs:
        return None
    return attrs


def extract_skill_use_events(
    content: str,
    available_skill_names: set[str],
    session_id: str,
    agent_id: str = "",
) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
    """Extract known Skill-use markers from model-visible content.

    Returns visible content, accepted UI events, and ignored declarations for logging.
    Malformed markers are left untouched so normal answer text is not accidentally removed.
    """
    if not content or "[skill_use" not in content:
        return content, [], []

    events: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    output_parts: list[str] = []
    cursor = 0

    for match in _SKILL_USE_RE.finditer(content):
        attrs = _parse_attrs(match.group("attrs"))
        if attrs is None:
            continue

        output_parts.append(content[cursor:match.start()])
        cursor = match.end()

        name = attrs["name"]
        phase = attrs.get("phase", "answering")
        reason = attrs.get("reason", "")

        if name not in available_skill_names:
            ignored.append({"name": name, "phase": phase, "reason": reason})
            continue

        events.append(
            {
                "type": "skill_use",
                "name": name,
                "phase": phase,
                "reason": reason,
                "session_id": session_id,
                "agent_id": agent_id,
            }
        )

    if not events and not ignored:
        return content, [], []

    output_parts.append(content[cursor:])
    return "".join(output_parts), events, ignored


def truncate_for_log(value: Any, max_length: int = 500) -> Any:
    """Recursively truncate large values before structured logging."""
    if isinstance(value, str):
        if len(value) <= max_length:
            return value
        return value[:max_length] + "...<truncated>"
    if isinstance(value, dict):
        return {key: truncate_for_log(item, max_length=max_length) for key, item in value.items()}
    if isinstance(value, list):
        return [truncate_for_log(item, max_length=max_length) for item in value]
    return value
```

- [ ] **Step 4: Run helper tests and verify they pass**

Run:

```bash
pytest tests/unit/test_chat_process.py -v
```

Expected: all tests in `tests/unit/test_chat_process.py` pass.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add harness/observability/__init__.py harness/observability/chat_process.py tests/unit/test_chat_process.py
git commit -m "feat: add chat process event helpers"
```

Expected: commit succeeds and only these two files are included.

---

### Task 2: Session Persistence for Process Events

**Files:**
- Modify: `gateway/session.py`
- Modify: `tests/unit/test_session.py`

- [ ] **Step 1: Write failing session persistence tests**

Append these tests to `tests/unit/test_session.py`:

```python
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
```

- [ ] **Step 2: Run session tests and verify they fail**

Run:

```bash
pytest tests/unit/test_session.py -v
```

Expected: fail because `SessionPersistence.write_message()` does not accept `process_events`.

- [ ] **Step 3: Implement persistence changes**

In `gateway/session.py`, replace `write_message` with:

```python
    def write_message(
        self,
        user_id: str,
        session_id: str,
        msg: BaseMessage | dict,
        agent_id: str = "",
        process_events: list[dict] | None = None,
    ) -> None:
        """Append a message to the session JSONL file."""
        path = self._session_path(user_id, session_id)

        if isinstance(msg, dict):
            record = {
                "timestamp": msg.get("timestamp") or datetime.now().isoformat(),
                "type": msg.get("type", ""),
                "content": msg.get("content", ""),
                "agent_id": msg.get("agent_id", agent_id),
            }
            if msg.get("tool_calls") is not None:
                record["tool_calls"] = msg.get("tool_calls", [])
            if msg.get("tool_call_id") is not None:
                record["tool_call_id"] = msg.get("tool_call_id")
            if msg.get("name") is not None:
                record["name"] = msg.get("name")
        else:
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

        if process_events is not None:
            record["process_events"] = process_events

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run session tests and verify they pass**

Run:

```bash
pytest tests/unit/test_session.py -v
```

Expected: all session persistence tests pass.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add gateway/session.py tests/unit/test_session.py
git commit -m "feat: persist chat process events"
```

Expected: commit succeeds and only these two files are included.

---

### Task 3: WebSocket Process Event Emission and Logging

**Files:**
- Modify: `gateway/server.py`
- Modify: `runtime/agent.py`
- Modify: `harness/expert/agent_factory.py`
- Test: `tests/unit/test_chat_process.py`
- Test: `tests/unit/test_chat_process_prompts.py`

- [ ] **Step 1: Add failing prompt builder tests**

Create `tests/unit/test_chat_process_prompts.py`:

```python
from types import SimpleNamespace

from runtime.context_schema import UserContext, UserRole


def _ctx() -> UserContext:
    return UserContext(
        user_id="u1",
        role=UserRole.OPERATOR,
        tenant_id="default",
        permissions=[],
        memory_path="",
        session_id="sess-1",
    )


def test_generic_system_prompt_includes_public_skill_use_protocol():
    from runtime.agent import build_generic_system_prompt

    prompt = build_generic_system_prompt(_ctx())

    assert "enterprise AI assistant" in prompt
    assert '[skill_use name="' in prompt
    assert "Do not include private reasoning" in prompt


def test_expert_system_prompt_preserves_soul_and_includes_public_skill_use_protocol():
    from harness.expert.agent_factory import build_expert_system_prompt

    profile = SimpleNamespace(display_name="Equipment Expert", description="Monitors equipment")

    prompt = build_expert_system_prompt(profile, "You are a domain expert.")

    assert "You are a domain expert." in prompt
    assert '[skill_use name="' in prompt
    assert "Do not include private reasoning" in prompt
```

- [ ] **Step 2: Run prompt tests and verify they fail**

Run:

```bash
pytest tests/unit/test_chat_process_prompts.py -v
```

Expected: fail because `build_generic_system_prompt` and `build_expert_system_prompt` do not exist yet.

- [ ] **Step 3: Add a generic system prompt builder**

In `runtime/agent.py`, add this import near the other imports:

```python
from harness.observability.chat_process import SKILL_USE_PROTOCOL_INSTRUCTION
```

Add this function above `create_agent_for_user`:

```python
def build_generic_system_prompt(user_ctx: UserContext) -> str:
    """Build the generic Agent prompt with the public Skill-use protocol."""
    return (
        f"You are an enterprise AI assistant. You are helping user '{user_ctx.user_id}' "
        f"with role '{user_ctx.role.value}'. Follow Skill instructions when available. "
        f"Be professional and practical.\n\n"
        f"--- PUBLIC PROCESS EVENTS ---\n{SKILL_USE_PROTOCOL_INSTRUCTION}\n--- END PUBLIC PROCESS EVENTS ---"
    )
```

Then replace the inline generic prompt assignment inside `create_agent_for_user` with:

```python
    system_prompt = build_generic_system_prompt(user_ctx)
```

- [ ] **Step 4: Add an expert system prompt builder**

In `harness/expert/agent_factory.py`, add this import near the other imports:

```python
from harness.observability.chat_process import SKILL_USE_PROTOCOL_INSTRUCTION
```

Add this function above `create_expert_agent`:

```python
def build_expert_system_prompt(profile: AgentProfile, soul_content: str) -> str:
    """Build an expert Agent prompt with the public Skill-use protocol."""
    base_prompt = soul_content or f"You are {profile.display_name}. {profile.description}"
    return (
        f"{base_prompt}\n\n"
        f"--- PUBLIC PROCESS EVENTS ---\n{SKILL_USE_PROTOCOL_INSTRUCTION}\n--- END PUBLIC PROCESS EVENTS ---"
    )
```

Then replace the inline expert prompt assignment inside `create_expert_agent` with:

```python
    system_prompt = build_expert_system_prompt(profile, soul_content)
```

- [ ] **Step 5: Run prompt tests and verify they pass**

Run:

```bash
pytest tests/unit/test_chat_process_prompts.py -v
```

Expected: both prompt tests pass.

- [ ] **Step 6: Wire Skill manifest event after `session_start`**

In `gateway/server.py`, add imports:

```python
from langchain_core.messages import ToolMessage
from harness.observability.chat_process import (
    build_progress_event,
    build_skill_manifest_event,
    build_tool_call_event,
    extract_skill_use_events,
    get_session_skill_infos,
    truncate_for_log,
)
```

Inside `ws_chat`, initialize session Skill state after `agent = None`:

```python
    agent = None
    session_skill_names: set[str] = set()
```

After sending the existing `session_start` event, add:

```python
        if not is_external:
            try:
                session_skills = get_session_skill_infos(skill_manager, user_ctx, profile)
                session_skill_names = {skill.name for skill in session_skills}
                session_skill_event = build_skill_manifest_event(session_skills, user_ctx, agent_id)
                await websocket.send_text(json.dumps(session_skill_event, ensure_ascii=False))
                logger.info(
                    "chat_skill_manifest_loaded",
                    user_id=user_ctx.user_id,
                    session_id=user_ctx.session_id,
                    agent_id=agent_id,
                    role=user_ctx.role.value,
                    skill_names=sorted(session_skill_names),
                )
            except Exception as exc:
                logger.warning(
                    "chat_skill_manifest_failed",
                    user_id=user_ctx.user_id,
                    session_id=user_ctx.session_id,
                    agent_id=agent_id,
                    error=str(exc),
                )
```

- [ ] **Step 7: Replace the internal Agent stream loop with process-event emission**

In the internal Agent branch of `ws_chat`, replace the existing `for chunk in agent.stream(...):` block with this structure:

```python
                turn_process_events: list[dict] = []
                turn_tool_calls: list[dict] = []
                full_response = ""

                progress_event = build_progress_event(
                    "preparing_response",
                    "Preparing response",
                    user_ctx,
                    agent_id,
                )
                turn_process_events.append(progress_event)
                await websocket.send_text(json.dumps(progress_event, ensure_ascii=False))
                logger.info(
                    "chat_progress_emitted",
                    user_id=user_ctx.user_id,
                    session_id=user_ctx.session_id,
                    agent_id=agent_id,
                    stage=progress_event["stage"],
                )

                session_persistence.write_message(
                    user_ctx.user_id,
                    user_ctx.session_id,
                    {"type": "human", "content": user_message},
                    agent_id=agent_id,
                )

                for chunk in agent.stream(
                    {"messages": [{"role": "user", "content": user_message}]},
                    config={"configurable": {"context": user_ctx}},
                    stream_mode="updates",
                ):
                    for node_output in chunk.values():
                        if not node_output or not isinstance(node_output, dict):
                            continue
                        for msg in node_output.get("messages", []):
                            msg_type = getattr(msg, "type", None)

                            if isinstance(msg, ToolMessage):
                                session_persistence.write_message(
                                    user_ctx.user_id,
                                    user_ctx.session_id,
                                    msg,
                                    agent_id=agent_id,
                                )
                                continue

                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    tool_event = build_tool_call_event(tc, user_ctx, agent_id)
                                    turn_tool_calls.append(
                                        {
                                            "id": tool_event["id"],
                                            "name": tool_event["name"],
                                            "args": tool_event["args"],
                                        }
                                    )
                                    turn_process_events.append(tool_event)
                                    await websocket.send_text(json.dumps(tool_event, ensure_ascii=False))
                                    logger.info(
                                        "chat_tool_call_emitted",
                                        user_id=user_ctx.user_id,
                                        session_id=user_ctx.session_id,
                                        agent_id=agent_id,
                                        tool_call_id=tool_event["id"],
                                        tool_name=tool_event["name"],
                                        args=truncate_for_log(tool_event["args"]),
                                    )

                            if hasattr(msg, "content") and msg.content and msg_type == "ai":
                                visible_content, skill_events, ignored_skill_uses = extract_skill_use_events(
                                    msg.content,
                                    available_skill_names=session_skill_names,
                                    session_id=user_ctx.session_id,
                                    agent_id=agent_id,
                                )
                                for skill_event in skill_events:
                                    turn_process_events.append(skill_event)
                                    await websocket.send_text(json.dumps(skill_event, ensure_ascii=False))
                                    logger.info(
                                        "chat_skill_use_declared",
                                        user_id=user_ctx.user_id,
                                        session_id=user_ctx.session_id,
                                        agent_id=agent_id,
                                        skill_name=skill_event["name"],
                                        phase=skill_event["phase"],
                                        reason=skill_event["reason"],
                                    )
                                for ignored in ignored_skill_uses:
                                    logger.info(
                                        "chat_skill_use_ignored",
                                        user_id=user_ctx.user_id,
                                        session_id=user_ctx.session_id,
                                        agent_id=agent_id,
                                        skill_name=ignored["name"],
                                        phase=ignored["phase"],
                                        reason=ignored["reason"],
                                    )
                                if visible_content:
                                    full_response += visible_content
                                    await websocket.send_text(json.dumps({
                                        "type": "chunk",
                                        "content": visible_content,
                                    }, ensure_ascii=False))

                session_persistence.write_message(
                    user_ctx.user_id,
                    user_ctx.session_id,
                    {
                        "type": "ai",
                        "content": full_response,
                        "tool_calls": turn_tool_calls,
                    },
                    agent_id=agent_id,
                    process_events=turn_process_events,
                )
```

Keep the external Agent branch unchanged except for using `ensure_ascii=False` when sending JSON if you touch those lines.

- [ ] **Step 8: Run backend tests**

Run:

```bash
pytest tests/unit/test_chat_process.py tests/unit/test_chat_process_prompts.py tests/unit/test_session.py -v
```

Expected: all three backend process/persistence test modules pass.

- [ ] **Step 9: Run a broader backend smoke test**

Run:

```bash
pytest tests/unit/test_imports.py tests/unit/test_skill.py tests/unit/test_rbac_resource_permissions.py -v
```

Expected: selected backend tests pass. These catch import cycles, Skill manager regressions, and RBAC filtering regressions.

- [ ] **Step 10: Commit Task 3**

Run:

```bash
git add gateway/server.py runtime/agent.py harness/expert/agent_factory.py tests/unit/test_chat_process.py tests/unit/test_chat_process_prompts.py
git commit -m "feat: stream chat process events"
```

Expected: commit succeeds and only Task 3 files are included.

---

### Task 4: Frontend Types and Chat Store

**Files:**
- Modify: `web/src/types/chat.ts`
- Modify: `web/src/store/chatStore.ts`
- Modify: `web/src/hooks/useAgentChat.ts`
- Test: `web/src/store/chatStore.test.ts`

- [ ] **Step 1: Write failing chat store tests**

Create `web/src/store/chatStore.test.ts`:

```typescript
import { beforeEach, describe, expect, test } from 'vitest';
import { useChatStore } from './chatStore';
import type { Message } from '../types/chat';

function resetStore() {
  useChatStore.setState({
    sessions: [],
    currentSessionId: '',
    messages: [],
    streamingContent: '',
    isStreaming: false,
    activeToolCalls: [],
    sessionSkills: [],
    sessionRole: '',
    activeProcessEvents: [],
  });
}

describe('chat process events', () => {
  beforeEach(() => {
    resetStore();
  });

  test('stores session skill manifest from stream events', () => {
    useChatStore.getState().handleStreamEvent({
      type: 'skill_manifest',
      role: 'operator',
      session_id: 'sess-1',
      skills: [
        { name: 'file_manager', description: 'Files', category: 'file_manager' },
        { name: 'knowledge_search', description: 'Search', category: 'knowledge_search' },
      ],
    });

    expect(useChatStore.getState().sessionRole).toBe('operator');
    expect(useChatStore.getState().sessionSkills.map((skill) => skill.name)).toEqual([
      'file_manager',
      'knowledge_search',
    ]);
  });

  test('seeds each user turn with loaded skill manifest and finalizes process events', () => {
    useChatStore.setState({
      sessionSkills: [{ name: 'file_manager', description: 'Files', category: 'file_manager' }],
      sessionRole: 'operator',
    });

    const userMessage: Message = {
      id: 'user-1',
      type: 'human',
      content: 'hello',
      timestamp: '2026-05-27T00:00:00.000Z',
    };

    useChatStore.getState().beginUserTurn(userMessage);
    useChatStore.getState().handleStreamEvent({
      type: 'skill_use',
      name: 'file_manager',
      phase: 'answering',
      reason: 'Need a file',
      session_id: 'sess-1',
    });
    useChatStore.getState().handleStreamEvent({ type: 'chunk', content: 'Answer' });
    useChatStore.getState().handleStreamEvent({ type: 'done' });

    const state = useChatStore.getState();
    expect(state.messages).toHaveLength(2);
    expect(state.messages[1].type).toBe('ai');
    expect(state.messages[1].process_events?.map((event) => event.type)).toEqual([
      'skill_manifest',
      'skill_use',
    ]);
    expect(state.activeProcessEvents).toEqual([]);
  });

  test('adds progress and tool calls to active process events', () => {
    useChatStore.getState().handleStreamEvent({
      type: 'progress',
      stage: 'preparing_response',
      content: 'Preparing response',
      session_id: 'sess-1',
    });
    useChatStore.getState().handleStreamEvent({
      type: 'tool_call',
      id: 'tc1',
      name: 'file_read',
      args: { path: 'a.txt' },
      session_id: 'sess-1',
    });

    const events = useChatStore.getState().activeProcessEvents;
    expect(events.map((event) => event.type)).toEqual(['progress', 'tool_call']);
    expect(useChatStore.getState().activeToolCalls[0].name).toBe('file_read');
  });
});
```

- [ ] **Step 2: Run chat store tests and verify they fail**

Run:

```bash
cd web
npm test -- src/store/chatStore.test.ts
```

Expected: fail because `sessionSkills`, `activeProcessEvents`, and `beginUserTurn` do not exist.

- [ ] **Step 3: Extend chat TypeScript types**

In `web/src/types/chat.ts`, replace the file with:

```typescript
export interface SkillSummary {
  name: string;
  description: string;
  category: string;
}

export interface ToolCallInfo {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export type ProcessEvent =
  | {
      id: string;
      type: 'skill_manifest';
      skills: SkillSummary[];
      role?: string;
      session_id?: string;
      agent_id?: string;
    }
  | {
      id: string;
      type: 'skill_use';
      name: string;
      phase?: string;
      reason?: string;
      session_id?: string;
      agent_id?: string;
    }
  | {
      id: string;
      type: 'progress';
      stage?: string;
      content?: string;
      session_id?: string;
      agent_id?: string;
    }
  | ({
      type: 'tool_call';
      session_id?: string;
      agent_id?: string;
    } & ToolCallInfo);

export interface Message {
  id: string;
  type: 'human' | 'ai' | 'tool';
  content: string;
  timestamp: string;
  tool_calls?: ToolCallInfo[];
  process_events?: ProcessEvent[];
}

export interface SessionInfo {
  id: string;
  title: string;
  lastMessageTime: string;
  agentId?: string;
}

export type StreamEventType =
  | 'session_start'
  | 'chunk'
  | 'tool_call'
  | 'skill_manifest'
  | 'skill_use'
  | 'progress'
  | 'done'
  | 'error';

export interface StreamEvent {
  type: StreamEventType;
  content?: string;
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
  skills?: SkillSummary[];
  role?: string;
  phase?: string;
  reason?: string;
  stage?: string;
  user_id?: string;
  session_id?: string;
  agent_id?: string;
}
```

- [ ] **Step 4: Extend chat store state and event handling**

In `web/src/store/chatStore.ts`:

1. Change the import to:

```typescript
import type { Message, ProcessEvent, SkillSummary, ToolCallInfo, SessionInfo, StreamEvent } from '../types/chat';
```

2. Add state fields and methods to `ChatState`:

```typescript
  sessionSkills: SkillSummary[];
  sessionRole: string;
  activeProcessEvents: ProcessEvent[];

  beginUserTurn: (message: Message) => void;
  addProcessEvent: (event: ProcessEvent) => void;
```

3. Add initial state:

```typescript
  sessionSkills: [],
  sessionRole: '',
  activeProcessEvents: [],
```

4. Add this helper above `useChatStore`:

```typescript
function processEventId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
```

5. In `loadSessionMessages`, map persisted process events:

```typescript
      process_events: m.process_events,
```

6. Replace `startNewSession` with:

```typescript
  startNewSession: () => set({
    messages: [],
    currentSessionId: '',
    streamingContent: '',
    isStreaming: false,
    activeToolCalls: [],
    activeProcessEvents: [],
    sessionSkills: [],
    sessionRole: '',
  }),
```

7. Add `beginUserTurn`:

```typescript
  beginUserTurn: (message: Message) => set((state) => {
    const seededEvents: ProcessEvent[] = state.sessionSkills.length
      ? [{
          id: processEventId('skills'),
          type: 'skill_manifest',
          skills: state.sessionSkills,
          role: state.sessionRole,
          session_id: state.currentSessionId,
        }]
      : [];

    return {
      messages: [...state.messages, message],
      streamingContent: '',
      isStreaming: true,
      activeToolCalls: [],
      activeProcessEvents: seededEvents,
    };
  }),
```

8. Replace `finalizeStream` with:

```typescript
  finalizeStream: () => set((state) => {
    if (!state.streamingContent) {
      return { isStreaming: false, activeProcessEvents: [], activeToolCalls: [] };
    }
    const newMessage: Message = {
      id: `${state.currentSessionId}-stream-${Date.now()}`,
      type: 'ai',
      content: state.streamingContent,
      timestamp: new Date().toISOString(),
      tool_calls: state.activeToolCalls,
      process_events: state.activeProcessEvents,
    };
    return {
      messages: [...state.messages, newMessage],
      streamingContent: '',
      isStreaming: false,
      activeToolCalls: [],
      activeProcessEvents: [],
    };
  }),
```

9. Add `addProcessEvent`:

```typescript
  addProcessEvent: (event: ProcessEvent) => set((state) => ({
    activeProcessEvents: [...state.activeProcessEvents, event],
  })),
```

10. Extend `handleStreamEvent`:

```typescript
      case 'skill_manifest':
        set({
          sessionSkills: event.skills || [],
          sessionRole: event.role || '',
        });
        if (state.isStreaming && event.skills?.length) {
          state.addProcessEvent({
            id: processEventId('skills'),
            type: 'skill_manifest',
            skills: event.skills,
            role: event.role,
            session_id: event.session_id,
            agent_id: event.agent_id,
          });
        }
        break;
      case 'skill_use':
        if (event.name) {
          state.addProcessEvent({
            id: processEventId('skill-use'),
            type: 'skill_use',
            name: event.name,
            phase: event.phase,
            reason: event.reason,
            session_id: event.session_id,
            agent_id: event.agent_id,
          });
        }
        break;
      case 'progress':
        state.addProcessEvent({
          id: processEventId('progress'),
          type: 'progress',
          stage: event.stage,
          content: event.content,
          session_id: event.session_id,
          agent_id: event.agent_id,
        });
        break;
```

11. Replace the `tool_call` case with:

```typescript
      case 'tool_call': {
        const toolCall = {
          id: event.id || processEventId('tc'),
          name: event.name || '',
          args: event.args || {},
        };
        state.addToolCall(toolCall);
        state.addProcessEvent({
          ...toolCall,
          type: 'tool_call',
          session_id: event.session_id,
          agent_id: event.agent_id,
        });
        break;
      }
```

12. Replace `resetStream` with:

```typescript
  resetStream: () => set({ streamingContent: '', isStreaming: false, activeToolCalls: [], activeProcessEvents: [] }),
```

- [ ] **Step 5: Start user turns through the store**

In `web/src/hooks/useAgentChat.ts`, replace the `send` callback body with:

```typescript
  const send = useCallback((content: string) => {
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      type: 'human',
      content,
      timestamp: new Date().toISOString(),
    };
    chatStore.beginUserTurn(userMessage);
    sendMessage(content);
  }, [chatStore, sendMessage]);
```

- [ ] **Step 6: Run chat store tests and verify they pass**

Run:

```bash
cd web
npm test -- src/store/chatStore.test.ts
```

Expected: all chat store tests pass.

- [ ] **Step 7: Commit Task 4**

Run:

```bash
git add web/src/types/chat.ts web/src/store/chatStore.ts web/src/hooks/useAgentChat.ts web/src/store/chatStore.test.ts
git commit -m "feat: track chat process events in frontend state"
```

Expected: commit succeeds and only Task 4 files are included.

---

### Task 5: Process Timeline UI

**Files:**
- Create: `web/src/components/ProcessTimeline.tsx`
- Modify: `web/src/components/StreamOutput.tsx`
- Modify: `web/src/components/ChatBubble.tsx`
- Modify: `web/src/pages/ChatPage.tsx`
- Test: `web/src/components/ProcessTimeline.test.tsx`

- [ ] **Step 1: Write failing ProcessTimeline tests**

Create `web/src/components/ProcessTimeline.test.tsx`:

```typescript
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import ProcessTimeline from './ProcessTimeline';
import type { ProcessEvent } from '../types/chat';

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

afterEach(() => cleanup());

const events: ProcessEvent[] = [
  {
    id: 'skills',
    type: 'skill_manifest',
    role: 'operator',
    skills: [{ name: 'file_manager', description: 'Files', category: 'file_manager' }],
  },
  {
    id: 'skill-use',
    type: 'skill_use',
    name: 'file_manager',
    phase: 'answering',
    reason: 'Need file context',
  },
  {
    id: 'tool',
    type: 'tool_call',
    name: 'file_read',
    args: { path: 'a.txt' },
  },
];

describe('ProcessTimeline', () => {
  test('renders a compact summary', () => {
    render(<ProcessTimeline events={events} />);

    expect(screen.getByText('Process')).toBeTruthy();
    expect(screen.getByText('1 Skills')).toBeTruthy();
    expect(screen.getByText('1 Skill use')).toBeTruthy();
    expect(screen.getByText('1 Tool')).toBeTruthy();
  });

  test('shows details when expanded', () => {
    render(<ProcessTimeline events={events} />);

    fireEvent.click(screen.getByText('Process'));

    expect(screen.getByText('Loaded Skills')).toBeTruthy();
    expect(screen.getByText('file_manager')).toBeTruthy();
    expect(screen.getByText('Using Skill')).toBeTruthy();
    expect(screen.getByText('file_read')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run ProcessTimeline tests and verify they fail**

Run:

```bash
cd web
npm test -- src/components/ProcessTimeline.test.tsx
```

Expected: fail because `ProcessTimeline` does not exist.

- [ ] **Step 3: Implement ProcessTimeline**

Create `web/src/components/ProcessTimeline.tsx`:

```typescript
import { Collapse, Space, Tag, Typography } from 'antd';
import type { ProcessEvent } from '../types/chat';

const { Text } = Typography;

interface ProcessTimelineProps {
  events?: ProcessEvent[];
}

function countEvents(events: ProcessEvent[], type: ProcessEvent['type']) {
  return events.filter((event) => event.type === type).length;
}

function renderEvent(event: ProcessEvent) {
  if (event.type === 'skill_manifest') {
    return (
      <div key={event.id} style={{ marginBottom: 8 }}>
        <Text strong>Loaded Skills</Text>
        <div style={{ marginTop: 6 }}>
          <Space size={[4, 4]} wrap>
            {event.skills.map((skill) => (
              <Tag key={skill.name}>{skill.name}</Tag>
            ))}
          </Space>
        </div>
      </div>
    );
  }

  if (event.type === 'skill_use') {
    return (
      <div key={event.id} style={{ marginBottom: 8 }}>
        <Text strong>Using Skill</Text>
        <div>
          <Tag color="blue">{event.name}</Tag>
          {event.phase && <Text type="secondary">{event.phase}</Text>}
        </div>
        {event.reason && <Text type="secondary">{event.reason}</Text>}
      </div>
    );
  }

  if (event.type === 'tool_call') {
    return (
      <div key={event.id} style={{ marginBottom: 8 }}>
        <Text strong>Tool Call</Text>
        <div>
          <Tag color="geekblue">{event.name}</Tag>
        </div>
        <pre style={{ margin: '6px 0 0', fontSize: 12, whiteSpace: 'pre-wrap' }}>
          {JSON.stringify(event.args, null, 2)}
        </pre>
      </div>
    );
  }

  return (
    <div key={event.id} style={{ marginBottom: 8 }}>
      <Text strong>{event.content || event.stage || 'Progress'}</Text>
    </div>
  );
}

export default function ProcessTimeline({ events = [] }: ProcessTimelineProps) {
  if (!events.length) return null;

  const skillManifest = events.find((event) => event.type === 'skill_manifest');
  const skillCount = skillManifest?.type === 'skill_manifest' ? skillManifest.skills.length : 0;
  const skillUseCount = countEvents(events, 'skill_use');
  const toolCount = countEvents(events, 'tool_call');

  const label = (
    <Space size={8} wrap>
      <Text strong>Process</Text>
      <Tag>{skillCount} Skills</Tag>
      <Tag>{skillUseCount} Skill use</Tag>
      <Tag>{toolCount} Tool</Tag>
    </Space>
  );

  return (
    <div style={{ marginBottom: 8 }}>
      <Collapse
        size="small"
        ghost
        items={[
          {
            key: 'process',
            label,
            children: <div>{events.map(renderEvent)}</div>,
          },
        ]}
      />
    </div>
  );
}
```

- [ ] **Step 4: Render active process events in StreamOutput**

In `web/src/components/StreamOutput.tsx`, import `ProcessTimeline`:

```typescript
import ProcessTimeline from './ProcessTimeline';
```

Change the store read to:

```typescript
  const { streamingContent, isStreaming, activeProcessEvents } = useChatStore();
```

Render the timeline above markdown:

```tsx
        <ProcessTimeline events={activeProcessEvents} />
        <ReactMarkdown>{streamingContent}</ReactMarkdown>
```

- [ ] **Step 5: Render persisted process events in ChatBubble**

In `web/src/components/ChatBubble.tsx`, import `ProcessTimeline`:

```typescript
import ProcessTimeline from './ProcessTimeline';
```

Inside the bubble, above `ReactMarkdown`, add:

```tsx
        {!isHuman && <ProcessTimeline events={message.process_events} />}
```

- [ ] **Step 6: Remove separate active tool-call rendering from ChatPage**

In `web/src/pages/ChatPage.tsx`, remove:

```typescript
import ToolCallCard from '../components/ToolCallCard';
```

Remove this rendering block:

```tsx
          {chatStore.activeToolCalls.map((tc) => (
            <ToolCallCard key={tc.id} toolCall={tc} />
          ))}
```

Tool calls now appear in `ProcessTimeline`.

- [ ] **Step 7: Run ProcessTimeline tests and chat store tests**

Run:

```bash
cd web
npm test -- src/components/ProcessTimeline.test.tsx src/store/chatStore.test.ts
```

Expected: both frontend test files pass.

- [ ] **Step 8: Commit Task 5**

Run:

```bash
git add web/src/components/ProcessTimeline.tsx web/src/components/StreamOutput.tsx web/src/components/ChatBubble.tsx web/src/pages/ChatPage.tsx web/src/components/ProcessTimeline.test.tsx
git commit -m "feat: show chat process timeline"
```

Expected: commit succeeds and only Task 5 files are included.

---

### Task 6: Final Verification and Browser Smoke Check

**Files:**
- Modify only if verification reveals a defect in files changed by Tasks 1-5.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
pytest tests/unit/test_chat_process.py tests/unit/test_chat_process_prompts.py tests/unit/test_session.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Run backend unit test suite**

Run:

```bash
pytest tests/unit -v
```

Expected: all unit tests pass. If unrelated environment-dependent tests fail, capture the exact failing test names and messages before deciding whether the failure is related.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd web
npm test
```

Expected: all Vitest tests pass.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd web
npm run build
```

Expected: TypeScript and Vite build finish with exit code 0.

- [ ] **Step 5: Run lint if available**

Check scripts:

```bash
cd web
npm run
```

Expected: no `lint` script is currently defined in `web/package.json`. Do not invent a lint command.

- [ ] **Step 6: Start local app for browser smoke check**

Use the project run script or start backend/frontend in the same way the repository already supports. On Windows PowerShell, prefer:

```powershell
.\run.bat
```

If the script starts long-running services, keep the process running until browser verification is complete.

- [ ] **Step 7: Browser verification**

Use the Browser plugin to open the local chat app URL printed by the run script, log in with an existing test account, send a simple message, and verify:

- the answer still streams;
- a process panel appears for the active answer;
- loaded Skills are visible in the panel;
- tool calls, when the Agent emits them, appear inside the same panel;
- the final AI message keeps the process panel after streaming completes;
- the browser console has no new runtime errors.

- [ ] **Step 8: Check backend logs**

Inspect `data/logs/gateway.log`:

```bash
Get-Content data\logs\gateway.log -Tail 200
```

Expected: relevant chat runs include `chat_skill_manifest_loaded` and `chat_progress_emitted`. Runs with tool calls include `chat_tool_call_emitted`; runs with valid Skill-use markers include `chat_skill_use_declared`.

- [ ] **Step 9: Final status check**

Run:

```bash
git status --short
```

Expected: no uncommitted files except intentional follow-up edits. Commit any verified fixes with a focused message before reporting completion.
