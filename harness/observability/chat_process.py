"""Helpers for public chat process events."""

from __future__ import annotations

import re
from typing import Any


SKILL_USE_PROTOCOL_INSTRUCTION = (
    'When using a public skill, include a marker like '
    '[skill_use name="skill_name" phase="planning" reason="short public reason"]. '
    "Do not include private reasoning."
)

_SKILL_USE_MARKER_RE = re.compile(r"\[skill_use\s+([^\]]*)\]")
_ATTR_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)="([^"]*)"')
_TRUNCATION_SUFFIX = "...<truncated>"


def skill_info_to_wire(skill: Any) -> dict[str, str]:
    """Serialize a skill info object for public process events."""
    category = getattr(skill, "category", "")
    return {
        "name": getattr(skill, "name", ""),
        "description": getattr(skill, "description", ""),
        "category": getattr(category, "value", category),
    }


def get_session_skill_infos(skill_manager: Any, user_ctx: Any, profile: Any | None = None) -> list[Any]:
    skills = list(skill_manager.list_skills_for_role(user_ctx.role))
    profile_skills = getattr(profile, "skills", None) if profile is not None else None
    if profile_skills is None:
        return skills

    allowed_names = set(profile_skills)
    return [skill for skill in skills if getattr(skill, "name", None) in allowed_names]


def build_skill_manifest_event(skills: list[Any], user_ctx: Any, agent_id: str = "") -> dict[str, Any]:
    return {
        "type": "skill_manifest",
        "skills": [skill_info_to_wire(skill) for skill in skills],
        "role": getattr(user_ctx.role, "value", user_ctx.role),
        "session_id": user_ctx.session_id,
        "agent_id": agent_id,
    }


def build_progress_event(stage: str, content: str, user_ctx: Any, agent_id: str = "") -> dict[str, str]:
    return {
        "type": "progress",
        "stage": stage,
        "content": content,
        "session_id": user_ctx.session_id,
        "agent_id": agent_id,
    }


def build_tool_call_event(tool_call: Any, user_ctx: Any, agent_id: str = "") -> dict[str, Any]:
    return {
        "type": "tool_call",
        "id": _read_field(tool_call, "id"),
        "name": _read_field(tool_call, "name"),
        "args": _read_field(tool_call, "args"),
        "session_id": user_ctx.session_id,
        "agent_id": agent_id,
    }


def extract_skill_use_events(
    content: str,
    available_skill_names: set[str],
    session_id: str,
    agent_id: str = "",
) -> tuple[str, list[dict[str, str]], list[dict[str, str]]]:
    accepted_events = []
    ignored_declarations = []
    visible_parts = []
    cursor = 0

    for match in _SKILL_USE_MARKER_RE.finditer(content):
        attrs = _parse_marker_attrs(match.group(1))
        if attrs is None:
            continue

        visible_parts.append(content[cursor : match.start()])
        cursor = match.end()

        declaration = {
            "name": attrs["name"],
            "phase": attrs["phase"],
            "reason": attrs["reason"],
        }
        if attrs["name"] not in available_skill_names:
            ignored_declarations.append(declaration)
            continue

        accepted_events.append(
            {
                "type": "skill_use",
                **declaration,
                "session_id": session_id,
                "agent_id": agent_id,
            }
        )

    visible_parts.append(content[cursor:])
    return "".join(visible_parts), accepted_events, ignored_declarations


def truncate_for_log(value: Any, max_length: int = 500) -> Any:
    if isinstance(value, str):
        if len(value) <= max_length:
            return value
        return value[:max_length] + _TRUNCATION_SUFFIX
    if isinstance(value, dict):
        return {key: truncate_for_log(item, max_length) for key, item in value.items()}
    if isinstance(value, list):
        return [truncate_for_log(item, max_length) for item in value]
    return value


def _read_field(value: Any, field: str) -> Any:
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)


def _parse_marker_attrs(raw_attrs: str) -> dict[str, str] | None:
    attrs = {}
    cursor = 0
    for match in _ATTR_RE.finditer(raw_attrs):
        if raw_attrs[cursor : match.start()].strip():
            return None
        attrs[match.group(1)] = match.group(2)
        cursor = match.end()

    if raw_attrs[cursor:].strip():
        return None
    if not {"name", "phase", "reason"}.issubset(attrs):
        return None
    return attrs
