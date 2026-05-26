"""Tests for resource-specific RBAC helpers."""

import yaml

from harness.security import rbac
from harness.skill.types import SkillAccess, SkillCategory, SkillInfo
from runtime.context_schema import UserRole


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

    assert _load(path)["rbac"]["roles"]["viewer"]["skills"] == [
        "admin_only",
        "report",
    ]


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
    assert roles["admin"]["skills"] == [
        "admin_only",
        "enterprise",
        "production",
        "report",
    ]
    assert roles["manager"]["skills"] == ["production", "report"]
    assert roles["operator"]["skills"] == ["enterprise", "production", "report"]
    assert roles["viewer"]["skills"] == ["report"]
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
    assert roles["admin"]["skills"] == ["production", "report"]
    assert roles["manager"]["skills"] == ["enterprise", "production", "report"]
    assert roles["operator"]["skills"] == ["report"]
    assert roles["viewer"]["skills"] == ["report"]


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
    assert roles["manager"]["mcp_tools"] == ["filesystem:read", "slack:post"]
    assert roles["operator"]["mcp_tools"] == ["other:*", "database:*"]
    assert roles["viewer"]["mcp_tools"] == ["database:*"]
    assert set(rbac.roles_for_mcp_server("database")) == {
        UserRole.ADMIN,
        UserRole.OPERATOR,
        UserRole.VIEWER,
    }
