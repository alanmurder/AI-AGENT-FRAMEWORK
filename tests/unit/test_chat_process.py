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
