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
