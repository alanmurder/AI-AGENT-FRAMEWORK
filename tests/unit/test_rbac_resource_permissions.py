"""Tests for resource-specific RBAC helpers."""

from types import SimpleNamespace

import pytest
import yaml

from harness.security import rbac
from harness.expert.validator import ExpertAgentValidator
from harness.expert.types import AgentProfile
from harness.skill.manager import SkillManager
from harness.skill.types import SkillAccess, SkillCategory, SkillInfo, SkillManifest
from runtime.context_schema import UserContext, UserRole


def _skill(name: str, access: SkillAccess) -> SkillInfo:
    return SkillInfo(
        name=name,
        description=f"{name} skill",
        category=SkillCategory.DATA_ANALYSIS,
        access=access,
        location=f"skills/{name}",
    )


def _write_rbac(tmp_path, config: dict):
    path = tmp_path / "rbac.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _configure(monkeypatch, tmp_path, config: dict):
    path = _write_rbac(tmp_path, config)
    monkeypatch.setattr(rbac, "DEFAULT_RBAC_CONFIG_PATH", str(path), raising=False)
    rbac.clear_rbac_caches()
    return path


def _import_server(monkeypatch):
    from runtime import models

    monkeypatch.setattr(
        models,
        "create_mini_model",
        lambda config: SimpleNamespace(),
    )

    from gateway import server

    return server


def teardown_function():
    rbac.clear_rbac_caches()


def test_role_allows_skill_uses_exact_skills_allow_list(tmp_path, monkeypatch):
    alpha = _skill("alpha", SkillAccess.REPORT)
    beta = _skill("beta", SkillAccess.ALL)
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skills": ["*"], "skill_access": "report"},
                    "manager": {"skills": ["alpha"], "skill_access": "all"},
                    "operator": {"skills": [], "skill_access": "all"},
                    "viewer": {"skills": [], "skill_access": "all"},
                }
            }
        },
    )

    assert rbac.role_allows_skill(UserRole.ADMIN, beta) is True
    assert rbac.role_allows_skill(UserRole.MANAGER, alpha) is True
    assert rbac.role_allows_skill(UserRole.MANAGER, beta) is False
    assert rbac.role_allows_skill(UserRole.OPERATOR, alpha) is False
    assert rbac.roles_for_skill("alpha", [alpha, beta]) == [
        UserRole.ADMIN,
        UserRole.MANAGER,
    ]


def test_role_allows_skill_falls_back_to_skill_access_without_skills_field(
    tmp_path, monkeypatch
):
    report = _skill("report", SkillAccess.REPORT)
    production = _skill("production", SkillAccess.PRODUCTION)
    enterprise = _skill("enterprise", SkillAccess.ENTERPRISE)
    all_access = _skill("all_access", SkillAccess.ALL)
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skill_access": "all"},
                    "manager": {"skill_access": "enterprise"},
                    "operator": {"skill_access": "production"},
                    "viewer": {"skill_access": "report"},
                }
            }
        },
    )

    assert rbac.role_allows_skill(UserRole.MANAGER, enterprise) is True
    assert rbac.role_allows_skill(UserRole.MANAGER, all_access) is False
    assert rbac.role_allows_skill(UserRole.OPERATOR, production) is True
    assert rbac.role_allows_skill(UserRole.OPERATOR, enterprise) is False
    assert rbac.role_allows_skill(UserRole.VIEWER, report) is True
    assert rbac.role_allows_skill(UserRole.VIEWER, production) is False


def test_role_allows_skill_defaults_to_all_when_skill_access_missing(
    tmp_path, monkeypatch
):
    report = _skill("report", SkillAccess.REPORT)
    enterprise = _skill("enterprise", SkillAccess.ENTERPRISE)
    all_access = _skill("admin_only", SkillAccess.ALL)
    path = _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "viewer": {"tools": [], "mcp_tools": []},
                }
            }
        },
    )

    assert rbac.get_role_skill_access(UserRole.VIEWER) == "all"
    assert rbac.role_allows_skill(UserRole.VIEWER, all_access) is True

    rbac.set_skill_roles("enterprise", [UserRole.ADMIN], [report, enterprise, all_access])

    viewer = _load(path)["rbac"]["roles"]["viewer"]
    assert "skills" not in viewer
    assert viewer["skills_denied"] == ["enterprise"]
    assert rbac.role_allows_skill(UserRole.VIEWER, all_access) is True


def test_set_skill_roles_materializes_effective_permissions_before_update(
    tmp_path, monkeypatch
):
    all_skills = [
        _skill("report", SkillAccess.REPORT),
        _skill("production", SkillAccess.PRODUCTION),
        _skill("enterprise", SkillAccess.ENTERPRISE),
        _skill("admin_only", SkillAccess.ALL),
    ]
    path = _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {
                        "tools": ["file_read", "file_write"],
                        "mcp_tools": ["*"],
                        "skill_access": "all",
                    },
                    "manager": {
                        "tools": ["file_read"],
                        "mcp_tools": ["filesystem:read"],
                        "skill_access": "enterprise",
                    },
                    "operator": {
                        "tools": ["file_read"],
                        "mcp_tools": [],
                        "skill_access": "production",
                    },
                    "viewer": {
                        "tools": ["file_read"],
                        "mcp_tools": [],
                        "skill_access": "report",
                    },
                }
            }
        },
    )

    rbac.set_skill_roles("enterprise", ["admin", UserRole.OPERATOR], all_skills)

    roles = _load(path)["rbac"]["roles"]
    assert "skills" not in roles["admin"]
    assert roles["manager"]["skills_denied"] == ["enterprise"]
    assert roles["operator"]["skills_allowed"] == ["enterprise"]
    assert "skills" not in roles["viewer"]
    assert roles["admin"]["tools"] == ["file_read", "file_write"]
    assert roles["admin"]["mcp_tools"] == ["*"]
    assert roles["manager"]["skill_access"] == "enterprise"


def test_set_skill_roles_materializes_roles_missing_skills_when_some_exist(
    tmp_path, monkeypatch
):
    all_skills = [
        _skill("report", SkillAccess.REPORT),
        _skill("production", SkillAccess.PRODUCTION),
        _skill("enterprise", SkillAccess.ENTERPRISE),
    ]
    path = _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skills": ["*"], "skill_access": "all"},
                    "manager": {"skill_access": "enterprise"},
                    "operator": {"skills": ["report"], "skill_access": "production"},
                    "viewer": {"skill_access": "report"},
                }
            }
        },
    )

    rbac.set_skill_roles("enterprise", [UserRole.MANAGER], all_skills)

    roles = _load(path)["rbac"]["roles"]
    assert roles["admin"]["skills"] == ["*"]
    assert roles["admin"]["skills_denied"] == ["enterprise"]
    assert "skills" not in roles["manager"]
    assert roles["operator"]["skills"] == ["report"]
    assert "skills" not in roles["viewer"]


def test_set_mcp_server_roles_replaces_only_target_server_entries(
    tmp_path, monkeypatch
):
    path = _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {
                        "mcp_tools": ["*", "database:query", "github:search"],
                    },
                    "manager": {
                        "mcp_tools": [
                            "filesystem:read",
                            "database:query",
                            "database:write",
                            "slack:post",
                        ],
                    },
                    "operator": {"mcp_tools": ["database:query", "other:*"]},
                    "viewer": {"mcp_tools": []},
                }
            }
        },
    )

    assert set(rbac.roles_for_mcp_server("database")) == {
        UserRole.ADMIN,
        UserRole.MANAGER,
        UserRole.OPERATOR,
    }

    rbac.set_mcp_server_roles("database", ["operator", UserRole.VIEWER])

    roles = _load(path)["rbac"]["roles"]
    assert roles["admin"]["mcp_tools"] == ["*", "github:search"]
    assert roles["admin"]["mcp_tools_denied"] == ["database:*"]
    assert roles["manager"]["mcp_tools"] == ["filesystem:read", "slack:post"]
    assert roles["operator"]["mcp_tools"] == ["other:*", "database:*"]
    assert roles["viewer"]["mcp_tools"] == ["database:*"]
    assert set(rbac.roles_for_mcp_server("database")) == {
        UserRole.OPERATOR,
        UserRole.VIEWER,
    }
    assert set(rbac.roles_for_mcp_server("future")) == {UserRole.ADMIN}
    assert rbac.mcp_tool_allowed("database:query", rbac.get_role_mcp_tool_access()[UserRole.ADMIN]) is False
    assert rbac.mcp_tool_allowed("future:query", rbac.get_role_mcp_tool_access()[UserRole.ADMIN]) is True


def test_skill_manager_list_skills_for_role_filters_with_exact_rbac(
    tmp_path, monkeypatch
):
    file_manager = _skill("file_manager", SkillAccess.PRODUCTION)
    database_query = _skill("database_query", SkillAccess.ENTERPRISE)
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skills": ["*"], "skill_access": "all"},
                    "manager": {"skills": [], "skill_access": "enterprise"},
                    "operator": {"skills": ["file_manager"], "skill_access": "all"},
                    "viewer": {"skills": [], "skill_access": "report"},
                }
            }
        },
    )

    manager = SkillManager.__new__(SkillManager)
    manager.list_skills = lambda: [file_manager, database_query]

    assert manager.list_skills_for_role(UserRole.OPERATOR) == [file_manager]


def test_skill_manager_generate_manifest_uses_exact_rbac_and_profile_allow_list(
    tmp_path, monkeypatch
):
    file_manager = _skill("file_manager", SkillAccess.PRODUCTION)
    database_query = _skill("database_query", SkillAccess.ENTERPRISE)
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "operator": {
                        "skills": ["database_query"],
                        "skill_access": "production",
                    },
                }
            }
        },
    )

    manager = SkillManager.__new__(SkillManager)
    manager.list_skills = lambda: [file_manager, database_query]

    class LegacyGenerator:
        def generate_text(self, user_skill_access=None, skill_names=None):
            skills = [file_manager]
            if skill_names is not None:
                skills = [skill for skill in skills if skill.name in skill_names]
            return SkillManifest(skills).to_text()

    manager.manifest_gen = LegacyGenerator()

    manifest = manager.generate_manifest("operator")
    assert "database_query" in manifest
    assert "file_manager" not in manifest

    manifest = manager.generate_manifest("operator", skill_names=["file_manager"])
    assert "database_query" not in manifest
    assert "file_manager" not in manifest


def test_set_skill_roles_preserves_wildcard_with_target_deny(
    tmp_path, monkeypatch
):
    report = _skill("report", SkillAccess.REPORT)
    database_query = _skill("database_query", SkillAccess.ENTERPRISE)
    future_skill = _skill("future_skill", SkillAccess.ALL)
    path = _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skills": ["*"], "skill_access": "all"},
                    "manager": {"skills": [], "skill_access": "enterprise"},
                    "operator": {"skill_access": "production"},
                    "viewer": {"skill_access": "report"},
                }
            }
        },
    )

    rbac.set_skill_roles("database_query", [UserRole.MANAGER], [report, database_query])

    roles = _load(path)["rbac"]["roles"]
    assert roles["admin"]["skills"] == ["*"]
    assert roles["admin"]["skills_denied"] == ["database_query"]
    assert roles["manager"]["skills"] == ["database_query"]
    assert "skills" not in roles["operator"]
    assert "skills" not in roles["viewer"]
    assert rbac.role_allows_skill(UserRole.ADMIN, database_query) is False
    assert rbac.role_allows_skill(UserRole.ADMIN, future_skill) is True


def test_expert_validator_filters_profile_skills_with_exact_rbac(
    tmp_path, monkeypatch
):
    all_skills = [
        _skill("file_manager", SkillAccess.PRODUCTION),
        _skill("database_query", SkillAccess.ENTERPRISE),
    ]
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skills": ["*"], "skill_access": "all"},
                    "manager": {"skills": [], "skill_access": "enterprise"},
                    "operator": {"skills": ["file_manager"], "skill_access": "all"},
                    "viewer": {"skills": [], "skill_access": "report"},
                }
            }
        },
    )

    assert ExpertAgentValidator.validate_skills_from_profile(
        "operator",
        ["file_manager", "database_query"],
        all_skills,
    ) == ["file_manager"]


def test_expert_validator_keeps_unknown_skills_only_without_known_skill_list(
    tmp_path, monkeypatch
):
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "operator": {"skills": [], "skill_access": "all"},
                }
            }
        },
    )

    with pytest.raises(ValueError, match="Unknown skill"):
        ExpertAgentValidator.validate_skills_from_profile(
            "operator",
            ["future_skill"],
            [],
        )
    assert ExpertAgentValidator.validate_skills_from_profile(
        "operator",
        ["future_skill"],
    ) == ["future_skill"]


@pytest.mark.asyncio
async def test_create_agent_passes_known_skills_to_validator(tmp_path, monkeypatch):
    file_manager = _skill("file_manager", SkillAccess.PRODUCTION)
    database_query = _skill("database_query", SkillAccess.ENTERPRISE)
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skills": ["*"], "skill_access": "all", "mcp_tools": ["*"]},
                    "operator": {
                        "skills": ["file_manager"],
                        "skill_access": "all",
                        "mcp_tools": [],
                    },
                }
            }
        },
    )

    server = _import_server(monkeypatch)

    captured = {}

    class FakeStore:
        def save_soul(self, name, content):
            return tmp_path / f"{name}.md"

        def save(self, profile):
            captured["profile"] = profile

    class FakeRegistry:
        store = FakeStore()

        def get(self, name):
            return None

        def register(self, profile):
            captured["registered"] = profile

    monkeypatch.setattr(
        server,
        "require_admin",
        lambda authorization=None: UserContext(user_id="admin", role=UserRole.ADMIN),
    )
    monkeypatch.setattr(server, "expert_registry", FakeRegistry())
    monkeypatch.setattr(
        server,
        "skill_manager",
        SimpleNamespace(list_skills=lambda: [file_manager, database_query]),
    )

    request = server.CreateAgentRequest(
        name="agent",
        display_name="Agent",
        description="Agent desc",
        role="operator",
        skills=["file_manager", "database_query"],
        mcp_tools=[],
    )

    response = await server.create_agent(request)

    assert response["agent"]["skills"] == ["file_manager"]
    assert captured["profile"].skills == ["file_manager"]


@pytest.mark.asyncio
async def test_create_agent_rejects_unknown_skill_names(tmp_path, monkeypatch):
    file_manager = _skill("file_manager", SkillAccess.PRODUCTION)
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skills": ["*"], "skill_access": "all", "mcp_tools": ["*"]},
                    "operator": {
                        "skills": ["file_manager"],
                        "skill_access": "all",
                        "mcp_tools": [],
                    },
                }
            }
        },
    )

    server = _import_server(monkeypatch)

    class FakeStore:
        def save_soul(self, name, content):
            return tmp_path / f"{name}.md"

        def save(self, profile):
            pass

    class FakeRegistry:
        store = FakeStore()

        def get(self, name):
            return None

        def register(self, profile):
            pass

    monkeypatch.setattr(
        server,
        "require_admin",
        lambda authorization=None: UserContext(user_id="admin", role=UserRole.ADMIN),
    )
    monkeypatch.setattr(server, "expert_registry", FakeRegistry())
    monkeypatch.setattr(
        server,
        "skill_manager",
        SimpleNamespace(list_skills=lambda: [file_manager]),
    )

    request = server.CreateAgentRequest(
        name="agent",
        display_name="Agent",
        description="Agent desc",
        role="operator",
        skills=["missing_skill"],
        mcp_tools=[],
    )

    with pytest.raises(Exception) as exc_info:
        await server.create_agent(request)

    assert getattr(exc_info.value, "status_code", None) == 400
    assert "Unknown skill" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_update_agent_refilters_existing_skills_when_role_changes(
    tmp_path, monkeypatch
):
    file_manager = _skill("file_manager", SkillAccess.PRODUCTION)
    database_query = _skill("database_query", SkillAccess.ENTERPRISE)
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skills": ["*"], "skill_access": "all", "mcp_tools": ["*"]},
                    "manager": {
                        "skills": ["file_manager", "database_query"],
                        "skill_access": "all",
                        "mcp_tools": [],
                    },
                    "operator": {
                        "skills": ["file_manager"],
                        "skill_access": "all",
                        "mcp_tools": [],
                    },
                }
            }
        },
    )

    server = _import_server(monkeypatch)

    profile = AgentProfile(
        name="agent",
        display_name="Agent",
        description="Agent desc",
        soul_file="agent.md",
        role="manager",
        skills=["file_manager", "database_query"],
        source="api",
    )
    captured = {}

    class FakeStore:
        def save(self, saved_profile):
            captured["profile"] = saved_profile

    class FakeRegistry:
        store = FakeStore()

        def get(self, name):
            return profile

        def register(self, saved_profile):
            captured["registered"] = saved_profile

    monkeypatch.setattr(
        server,
        "require_admin",
        lambda authorization=None: UserContext(user_id="admin", role=UserRole.ADMIN),
    )
    monkeypatch.setattr(server, "expert_registry", FakeRegistry())
    monkeypatch.setattr(
        server,
        "skill_manager",
        SimpleNamespace(list_skills=lambda: [file_manager, database_query]),
    )

    request = server.UpdateAgentRequest(role="operator")

    response = await server.update_agent("agent", request)

    assert response["agent"]["role"] == "operator"
    assert response["agent"]["skills"] == ["file_manager"]
    assert captured["profile"].skills == ["file_manager"]


@pytest.mark.asyncio
async def test_update_agent_refilters_existing_mcp_tools_when_role_changes(
    tmp_path, monkeypatch
):
    _configure(
        monkeypatch,
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {"skills": ["*"], "skill_access": "all", "mcp_tools": ["*"]},
                    "manager": {
                        "skills": [],
                        "skill_access": "all",
                        "mcp_tools": ["filesystem:read", "database:query"],
                    },
                    "operator": {
                        "skills": [],
                        "skill_access": "all",
                        "mcp_tools": ["filesystem:read"],
                    },
                }
            }
        },
    )

    server = _import_server(monkeypatch)

    profile = AgentProfile(
        name="agent",
        display_name="Agent",
        description="Agent desc",
        soul_file="agent.md",
        role="manager",
        skills=[],
        mcp_tools=["filesystem:read", "database:query"],
        source="api",
    )
    captured = {}

    class FakeStore:
        def save(self, saved_profile):
            captured["profile"] = saved_profile

    class FakeRegistry:
        store = FakeStore()

        def get(self, name):
            return profile

        def register(self, saved_profile):
            captured["registered"] = saved_profile

    monkeypatch.setattr(
        server,
        "require_admin",
        lambda authorization=None: UserContext(user_id="admin", role=UserRole.ADMIN),
    )
    monkeypatch.setattr(server, "expert_registry", FakeRegistry())
    monkeypatch.setattr(
        server,
        "skill_manager",
        SimpleNamespace(list_skills=lambda: []),
    )

    request = server.UpdateAgentRequest(role="operator")

    response = await server.update_agent("agent", request)

    assert response["agent"]["role"] == "operator"
    assert response["agent"]["mcp_tools"] == ["filesystem:read"]
    assert captured["profile"].mcp_tools == ["filesystem:read"]
