"""API tests for RBAC-managed resource permissions."""

from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from harness.mcp.types import MCPServerConfig
from harness.security import rbac
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


@pytest.fixture
def rbac_api(tmp_path, monkeypatch):
    from runtime import models

    monkeypatch.setattr(
        models,
        "create_mini_model",
        lambda config: SimpleNamespace(),
    )

    from gateway import server

    file_manager = _skill("file_manager", SkillAccess.PRODUCTION)
    database_query = _skill("database_query", SkillAccess.PRODUCTION)
    servers = {
        "filesystem": MCPServerConfig(name="filesystem", enabled=True),
        "github": MCPServerConfig(name="github", enabled=False),
    }

    path = _write_rbac(
        tmp_path,
        {
            "rbac": {
                "roles": {
                    "admin": {
                        "skills": ["*"],
                        "skill_access": "all",
                        "mcp_tools": ["*"],
                    },
                    "manager": {
                        "skills": ["database_query"],
                        "skill_access": "enterprise",
                        "mcp_tools": ["github:search"],
                    },
                    "operator": {
                        "skills": ["file_manager"],
                        "skill_access": "all",
                        "mcp_tools": ["filesystem:read"],
                    },
                    "viewer": {
                        "skills": [],
                        "skill_access": "report",
                        "mcp_tools": [],
                    },
                }
            }
        },
    )
    monkeypatch.setattr(rbac, "DEFAULT_RBAC_CONFIG_PATH", str(path), raising=False)
    rbac.clear_rbac_caches()

    monkeypatch.setattr(
        server,
        "require_admin",
        lambda authorization=None: UserContext(user_id="admin", role=UserRole.ADMIN),
    )
    monkeypatch.setattr(
        server,
        "authenticate_optional",
        lambda authorization=None: UserContext(user_id="admin", role=UserRole.ADMIN),
    )
    monkeypatch.setattr(
        server,
        "skill_manager",
        SimpleNamespace(list_skills=lambda: [file_manager, database_query]),
    )
    monkeypatch.setattr(
        server,
        "mcp_manager",
        SimpleNamespace(
            list_servers=lambda: list(servers.values()),
            get_server=lambda name: servers.get(name),
        ),
    )

    yield SimpleNamespace(
        client=TestClient(server.app),
        path=path,
        skills=[file_manager, database_query],
    )

    rbac.clear_rbac_caches()


def test_get_rbac_resources_returns_roles_skills_and_mcp_servers(rbac_api):
    response = rbac_api.client.get("/api/rbac/resources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["roles"] == [role.value for role in UserRole]
    assert payload["skills"] == [
        {
            "name": "file_manager",
            "description": "file_manager skill",
            "access": "production",
            "roles": ["admin", "operator"],
        },
        {
            "name": "database_query",
            "description": "database_query skill",
            "access": "production",
            "roles": ["admin", "manager"],
        },
    ]
    assert payload["mcp_servers"] == [
        {"name": "filesystem", "enabled": True, "roles": ["admin", "operator"]},
        {"name": "github", "enabled": False, "roles": ["admin", "manager"]},
    ]


def test_put_skill_roles_updates_yaml(rbac_api):
    response = rbac_api.client.put(
        "/api/rbac/skills/database_query/roles",
        json={"roles": ["manager", "viewer"]},
    )

    assert response.status_code == 200
    assert response.json() == {"name": "database_query", "roles": ["manager", "viewer"]}
    roles = _load(rbac_api.path)["rbac"]["roles"]
    assert roles["admin"]["skills"] == ["*"]
    assert roles["admin"]["skills_denied"] == ["database_query"]
    assert roles["manager"]["skills"] == ["database_query"]
    assert roles["operator"]["skills"] == ["file_manager"]
    assert roles["viewer"]["skills"] == ["database_query"]


def test_put_skill_roles_rejects_unknown_skill(rbac_api):
    response = rbac_api.client.put(
        "/api/rbac/skills/missing/roles",
        json={"roles": ["manager"]},
    )

    assert response.status_code == 404


def test_put_skill_roles_accepts_encoded_slash_skill_name(rbac_api, monkeypatch):
    folder_skill = _skill("folder/skill", SkillAccess.PRODUCTION)

    from gateway import server

    monkeypatch.setattr(
        server,
        "skill_manager",
        SimpleNamespace(list_skills=lambda: [*rbac_api.skills, folder_skill]),
    )

    response = rbac_api.client.put(
        "/api/rbac/skills/folder%2Fskill/roles",
        json={"roles": ["admin"]},
    )

    assert response.status_code == 200
    assert response.json() == {"name": "folder/skill", "roles": ["admin"]}


def test_put_skill_roles_rejects_invalid_role(rbac_api):
    response = rbac_api.client.put(
        "/api/rbac/skills/file_manager/roles",
        json={"roles": ["bogus"]},
    )

    assert response.status_code == 400


def test_put_mcp_server_roles_updates_yaml(rbac_api):
    response = rbac_api.client.put(
        "/api/rbac/mcp-servers/filesystem/roles",
        json={"roles": ["viewer"]},
    )

    assert response.status_code == 200
    assert response.json() == {"name": "filesystem", "roles": ["viewer"]}
    roles = _load(rbac_api.path)["rbac"]["roles"]
    assert roles["admin"]["mcp_tools"] == ["*"]
    assert roles["admin"]["mcp_tools_denied"] == ["filesystem:*"]
    assert roles["manager"]["mcp_tools"] == ["github:search"]
    assert roles["operator"]["mcp_tools"] == []
    assert roles["viewer"]["mcp_tools"] == ["filesystem:*"]

    resources = rbac_api.client.get("/api/rbac/resources").json()
    filesystem = next(s for s in resources["mcp_servers"] if s["name"] == "filesystem")
    assert filesystem["roles"] == ["viewer"]


def test_put_mcp_server_roles_rejects_unknown_server(rbac_api):
    response = rbac_api.client.put(
        "/api/rbac/mcp-servers/missing/roles",
        json={"roles": ["manager"]},
    )

    assert response.status_code == 404


def test_put_mcp_server_roles_accepts_encoded_slash_server_name(rbac_api, monkeypatch):
    from gateway import server

    servers = {
        "filesystem": MCPServerConfig(name="filesystem", enabled=True),
        "github": MCPServerConfig(name="github", enabled=False),
        "folder/server": MCPServerConfig(name="folder/server", enabled=True),
    }
    monkeypatch.setattr(
        server,
        "mcp_manager",
        SimpleNamespace(
            list_servers=lambda: list(servers.values()),
            get_server=lambda name: servers.get(name),
        ),
    )

    response = rbac_api.client.put(
        "/api/rbac/mcp-servers/folder%2Fserver/roles",
        json={"roles": ["viewer"]},
    )

    assert response.status_code == 200
    assert response.json() == {"name": "folder/server", "roles": ["viewer"]}


def test_put_mcp_server_roles_rejects_invalid_role(rbac_api):
    response = rbac_api.client.put(
        "/api/rbac/mcp-servers/filesystem/roles",
        json={"roles": ["bogus"]},
    )

    assert response.status_code == 400


def test_role_skills_endpoint_uses_exact_rbac_skill_allow_list(rbac_api):
    response = rbac_api.client.get("/api/roles/operator/skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "operator"
    assert payload["skill_access"] == "all"
    allowed_by_name = {skill["name"]: skill["allowed"] for skill in payload["skills"]}
    assert allowed_by_name == {
        "file_manager": True,
        "database_query": False,
    }


def test_list_skills_requires_authentication(monkeypatch):
    from runtime import models

    monkeypatch.setattr(
        models,
        "create_mini_model",
        lambda config: SimpleNamespace(),
    )

    from gateway import server

    client = TestClient(server.app)

    assert client.get("/api/skills").status_code == 401


def test_list_skills_filters_by_authenticated_role(rbac_api, monkeypatch):
    from gateway import server

    monkeypatch.setattr(
        server,
        "authenticate_optional",
        lambda authorization=None: UserContext(user_id="operator", role=UserRole.OPERATOR),
    )

    class FakeSkillManager:
        def list_skills_for_role(self, role):
            assert role == UserRole.OPERATOR
            return [rbac_api.skills[0]]

    monkeypatch.setattr(server, "skill_manager", FakeSkillManager())

    response = rbac_api.client.get("/api/skills", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["skills"] == [
        {
            "name": "file_manager",
            "description": "file_manager skill",
            "category": "data_analysis",
            "access": "production",
            "version": "1.0.0",
            "location": "skills/file_manager",
        }
    ]
    assert SkillManifest(rbac_api.skills[:1]).to_text() == payload["manifest"]


def test_rbac_resource_endpoints_require_admin(monkeypatch):
    from runtime import models

    monkeypatch.setattr(
        models,
        "create_mini_model",
        lambda config: SimpleNamespace(),
    )

    from gateway import server

    client = TestClient(server.app)

    assert client.get("/api/rbac/resources").status_code == 401
    assert client.put(
        "/api/rbac/skills/file_manager/roles",
        json={"roles": ["admin"]},
    ).status_code == 401
    assert client.put(
        "/api/rbac/mcp-servers/filesystem/roles",
        json={"roles": ["admin"]},
    ).status_code == 401
