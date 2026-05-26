# Resource Role Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins configure Skill role permissions and MCP service role permissions from the resource management pages while keeping `config/rbac.yaml` as the single effective permission source.

**Architecture:** Add RBAC helper functions that read and update exact Skill allow-lists plus service-level MCP grants. Expose admin-only FastAPI endpoints for resource permission reads and writes, then wire Skill and MCP management pages to those endpoints. Existing expert-agent and runtime filtering should use the same helpers, so UI-visible permissions and actual permissions match.

**Tech Stack:** Python 3.12, FastAPI, PyYAML, pytest, React 18, TypeScript, Zustand, Ant Design, Vitest, Testing Library.

---

## File Structure

- Modify `harness/security/rbac.py`: add exact Skill permission helpers, MCP service role helpers, YAML save support, and cache clearing.
- Modify `harness/skill/manifest.py`: allow `ManifestGenerator.generate()` to filter via explicit allowed Skill names from RBAC.
- Modify `harness/skill/manager.py`: add `get_skill()` and role-aware `list_skills_for_role()`.
- Modify `harness/expert/validator.py`: validate Skills and MCP tools through shared RBAC helpers.
- Modify `gateway/server.py`: add `/api/rbac/resources`, `/api/rbac/skills/{skill_name}/roles`, and `/api/rbac/mcp-servers/{server_name}/roles`; update role-filtered endpoints to use helpers.
- Add `tests/unit/test_rbac_resource_permissions.py`: backend RBAC helper and validation coverage.
- Add `tests/unit/test_rbac_resource_api.py`: API endpoint coverage with test client and temporary RBAC file.
- Modify `web/src/types/api.ts`: add RBAC resource and update request/response types.
- Add `web/src/api/rbac.ts`: frontend API client for RBAC resource permissions.
- Modify `web/src/store/adminStore.ts`: store RBAC resource state and expose update helpers.
- Modify `web/src/store/mcpStore.ts`: store RBAC resource state for MCP page or call RBAC API directly from the page.
- Modify `web/src/components/SkillManager.tsx`: render and save Skill role checkboxes.
- Modify `web/src/pages/MCPServerManager.tsx`: render and save MCP server role checkboxes.
- Add `web/src/components/SkillManager.test.tsx`: frontend Skill permission UI coverage.
- Add `web/src/pages/MCPServerManager.test.tsx`: frontend MCP permission UI coverage.

---

### Task 1: Backend RBAC Helpers

**Files:**
- Modify: `harness/security/rbac.py`
- Test: `tests/unit/test_rbac_resource_permissions.py`

- [ ] **Step 1: Write failing RBAC helper tests**

Create `tests/unit/test_rbac_resource_permissions.py`:

```python
from pathlib import Path

import pytest
import yaml

from harness.security import rbac
from harness.skill.types import SkillAccess, SkillCategory, SkillInfo
from runtime.context_schema import UserRole


def write_rbac(path: Path, roles: dict) -> Path:
    path.write_text(yaml.safe_dump({"rbac": {"roles": roles}}, sort_keys=False), encoding="utf-8")
    return path


def skill(name: str, access: SkillAccess = SkillAccess.REPORT) -> SkillInfo:
    return SkillInfo(
        name=name,
        description=f"{name} desc",
        category=SkillCategory.FILE_MANAGER,
        access=access,
        location=f"/tmp/{name}/SKILL.md",
    )


def test_role_allows_skill_uses_precise_skills_even_when_empty(tmp_path, monkeypatch):
    cfg = write_rbac(
        tmp_path / "rbac.yaml",
        {
            "admin": {"tools": [], "mcp_tools": ["*"], "skill_access": "all", "skills": ["*"]},
            "operator": {"tools": [], "mcp_tools": [], "skill_access": "production", "skills": []},
        },
    )
    monkeypatch.setattr(rbac, "DEFAULT_RBAC_CONFIG_PATH", str(cfg))
    rbac.clear_rbac_caches()

    assert rbac.role_allows_skill(UserRole.ADMIN, skill("file_manager", SkillAccess.ALL))
    assert not rbac.role_allows_skill(UserRole.OPERATOR, skill("file_manager", SkillAccess.REPORT))


def test_role_allows_skill_falls_back_to_skill_access_without_skills_field(tmp_path, monkeypatch):
    cfg = write_rbac(
        tmp_path / "rbac.yaml",
        {
            "operator": {"tools": [], "mcp_tools": [], "skill_access": "production"},
        },
    )
    monkeypatch.setattr(rbac, "DEFAULT_RBAC_CONFIG_PATH", str(cfg))
    rbac.clear_rbac_caches()

    assert rbac.role_allows_skill(UserRole.OPERATOR, skill("report_generator", SkillAccess.REPORT))
    assert rbac.role_allows_skill(UserRole.OPERATOR, skill("schedule_manager", SkillAccess.PRODUCTION))
    assert not rbac.role_allows_skill(UserRole.OPERATOR, skill("database_query", SkillAccess.ENTERPRISE))


def test_set_skill_roles_materializes_existing_effective_permissions(tmp_path, monkeypatch):
    cfg = write_rbac(
        tmp_path / "rbac.yaml",
        {
            "admin": {"tools": ["file_read"], "mcp_tools": ["*"], "skill_access": "all"},
            "manager": {"tools": [], "mcp_tools": [], "skill_access": "enterprise"},
            "operator": {"tools": [], "mcp_tools": [], "skill_access": "production"},
            "viewer": {"tools": [], "mcp_tools": [], "skill_access": "report"},
        },
    )
    monkeypatch.setattr(rbac, "DEFAULT_RBAC_CONFIG_PATH", str(cfg))
    rbac.clear_rbac_caches()
    all_skills = [
        skill("file_manager", SkillAccess.REPORT),
        skill("schedule_manager", SkillAccess.PRODUCTION),
        skill("database_query", SkillAccess.ENTERPRISE),
    ]

    rbac.set_skill_roles("schedule_manager", [UserRole.ADMIN, UserRole.VIEWER], all_skills)

    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    roles = saved["rbac"]["roles"]
    assert roles["admin"]["tools"] == ["file_read"]
    assert "schedule_manager" in roles["admin"]["skills"]
    assert "schedule_manager" in roles["viewer"]["skills"]
    assert "schedule_manager" not in roles["operator"]["skills"]
    assert "file_manager" in roles["operator"]["skills"]
    assert "database_query" not in roles["operator"]["skills"]


def test_set_mcp_server_roles_replaces_service_entries_only(tmp_path, monkeypatch):
    cfg = write_rbac(
        tmp_path / "rbac.yaml",
        {
            "admin": {"tools": [], "mcp_tools": ["*", "database:query"], "skill_access": "all"},
            "operator": {
                "tools": [],
                "mcp_tools": ["filesystem:read", "filesystem:write", "github:*"],
                "skill_access": "production",
            },
            "viewer": {"tools": [], "mcp_tools": ["filesystem:*"], "skill_access": "report"},
        },
    )
    monkeypatch.setattr(rbac, "DEFAULT_RBAC_CONFIG_PATH", str(cfg))
    rbac.clear_rbac_caches()

    rbac.set_mcp_server_roles("filesystem", [UserRole.OPERATOR])

    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    roles = saved["rbac"]["roles"]
    assert roles["admin"]["mcp_tools"] == ["*", "database:query"]
    assert roles["operator"]["mcp_tools"] == ["github:*", "filesystem:*"]
    assert roles["viewer"]["mcp_tools"] == []
```

- [ ] **Step 2: Run RBAC helper tests and verify they fail**

Run: `pytest tests/unit/test_rbac_resource_permissions.py -q`

Expected: FAIL because `clear_rbac_caches`, `role_allows_skill`, `set_skill_roles`, and `set_mcp_server_roles` do not exist yet.

- [ ] **Step 3: Implement RBAC helper functions**

Modify `harness/security/rbac.py`. Keep existing functions and add the following concrete implementation pieces:

```python
DEFAULT_RBAC_CONFIG_PATH = "config/rbac.yaml"


def load_rbac_config(yaml_path: str | None = None) -> dict:
    """Load RBAC configuration from YAML file."""
    path = Path(yaml_path or DEFAULT_RBAC_CONFIG_PATH)
    if not path.exists():
        raise FileNotFoundError(f"RBAC config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_rbac_config(rbac_config: dict, yaml_path: str | None = None) -> None:
    path = Path(yaml_path or DEFAULT_RBAC_CONFIG_PATH)
    path.write_text(yaml.safe_dump(rbac_config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    clear_rbac_caches()


def clear_rbac_caches() -> None:
    global _ROLE_TOOL_ACCESS_CACHE, _ROLE_MCP_TOOL_ACCESS_CACHE
    _ROLE_TOOL_ACCESS_CACHE = None
    _ROLE_MCP_TOOL_ACCESS_CACHE = None


def _roles_section(rbac_config: dict) -> dict:
    return rbac_config.setdefault("rbac", {}).setdefault("roles", {})


def _role_data(rbac_config: dict, role: UserRole) -> dict:
    return _roles_section(rbac_config).setdefault(role.value, {})


def normalize_roles(roles: list[str] | list[UserRole]) -> list[UserRole]:
    normalized = []
    for role in roles:
        normalized.append(role if isinstance(role, UserRole) else UserRole(role))
    return normalized


def role_allows_skill(role: UserRole, skill) -> bool:
    config_data = load_rbac_config()
    data = _roles_section(config_data).get(role.value, {})
    if "skills" in data:
        allowed = data.get("skills") or []
        return "*" in allowed or skill.name in allowed

    from harness.skill.types import SkillAccess

    max_level = SkillAccess.max_for_role(data.get("skill_access", role.value))
    return skill.access.level <= max_level


def roles_for_skill(skill_name: str, all_skills: list) -> list[UserRole]:
    target = next((s for s in all_skills if s.name == skill_name), None)
    if target is None:
        return []
    return [role for role in UserRole if role_allows_skill(role, target)]


def _materialize_skill_permissions(rbac_config: dict, all_skills: list) -> None:
    roles = _roles_section(rbac_config)
    needs_materialization = not any("skills" in data for data in roles.values())
    if not needs_materialization:
        return

    from harness.skill.types import SkillAccess

    for role in UserRole:
        data = roles.setdefault(role.value, {})
        max_level = SkillAccess.max_for_role(data.get("skill_access", role.value))
        data["skills"] = [s.name for s in all_skills if s.access.level <= max_level]


def set_skill_roles(skill_name: str, roles: list[str] | list[UserRole], all_skills: list) -> None:
    if not any(s.name == skill_name for s in all_skills):
        raise ValueError(f"Unknown skill: {skill_name}")

    selected = set(normalize_roles(roles))
    config_data = load_rbac_config()
    _materialize_skill_permissions(config_data, all_skills)

    for role in UserRole:
        data = _role_data(config_data, role)
        current = [s for s in data.get("skills", []) if s != skill_name and s != "*"]
        if role in selected:
            current.append(skill_name)
        data["skills"] = sorted(dict.fromkeys(current))

    save_rbac_config(config_data)


def _mcp_server_pattern(server_name: str) -> str:
    return f"{server_name}:*"


def _is_mcp_entry_for_server(entry: str, server_name: str) -> bool:
    return entry == _mcp_server_pattern(server_name) or entry.startswith(f"{server_name}:")


def roles_for_mcp_server(server_name: str) -> list[UserRole]:
    access = get_role_mcp_tool_access()
    result = []
    for role, entries in access.items():
        if "*" in entries or _mcp_server_pattern(server_name) in entries:
            result.append(role)
    return result


def set_mcp_server_roles(server_name: str, roles: list[str] | list[UserRole]) -> None:
    selected = set(normalize_roles(roles))
    config_data = load_rbac_config()
    for role in UserRole:
        data = _role_data(config_data, role)
        current = [e for e in data.get("mcp_tools", []) if not _is_mcp_entry_for_server(e, server_name)]
        if role in selected:
            current.append(_mcp_server_pattern(server_name))
        data["mcp_tools"] = current
    save_rbac_config(config_data)
```

Update existing `get_role_tool_access()`, `get_role_mcp_tool_access()`, and `get_role_skill_access()` calls so they call `load_rbac_config()` without hard-coded path assumptions.

- [ ] **Step 4: Run RBAC helper tests and verify they pass**

Run: `pytest tests/unit/test_rbac_resource_permissions.py -q`

Expected: PASS.

- [ ] **Step 5: Commit backend helper changes**

```bash
git add harness/security/rbac.py tests/unit/test_rbac_resource_permissions.py
git commit -m "feat: add resource permission rbac helpers"
```

---

### Task 2: Skill Filtering Integration

**Files:**
- Modify: `harness/skill/manifest.py`
- Modify: `harness/skill/manager.py`
- Modify: `harness/expert/validator.py`
- Test: `tests/unit/test_rbac_resource_permissions.py`

- [ ] **Step 1: Add failing integration tests for Skill filtering and expert validation**

Append to `tests/unit/test_rbac_resource_permissions.py`:

```python
def test_skill_manager_filters_with_precise_role_skills(tmp_path, monkeypatch):
    cfg = write_rbac(
        tmp_path / "rbac.yaml",
        {
            "operator": {"tools": [], "mcp_tools": [], "skill_access": "production", "skills": ["file_manager"]},
        },
    )
    monkeypatch.setattr(rbac, "DEFAULT_RBAC_CONFIG_PATH", str(cfg))
    rbac.clear_rbac_caches()

    from harness.skill.manager import SkillManager

    manager = SkillManager.__new__(SkillManager)
    manager.manifest_gen = type(
        "FakeManifestGen",
        (),
        {
            "generate": lambda self, user_skill_access=None, skill_names=None: type(
                "Manifest",
                (),
                {
                    "skills": [
                        s
                        for s in [skill("file_manager"), skill("database_query", SkillAccess.ENTERPRISE)]
                        if skill_names is None or s.name in skill_names
                    ],
                    "to_text": lambda self: "\n".join(sk.name for sk in self.skills),
                },
            )()
        },
    )()

    filtered = manager.list_skills_for_role(UserRole.OPERATOR)
    assert [s.name for s in filtered] == ["file_manager"]


def test_expert_validator_rejects_disallowed_precise_skill(tmp_path, monkeypatch):
    cfg = write_rbac(
        tmp_path / "rbac.yaml",
        {
            "operator": {"tools": [], "mcp_tools": [], "skill_access": "production", "skills": ["file_manager"]},
        },
    )
    monkeypatch.setattr(rbac, "DEFAULT_RBAC_CONFIG_PATH", str(cfg))
    rbac.clear_rbac_caches()

    from harness.expert.validator import ExpertAgentValidator

    all_skills = [skill("file_manager"), skill("database_query", SkillAccess.ENTERPRISE)]
    valid = ExpertAgentValidator.validate_skills_from_profile("operator", ["file_manager", "database_query"], all_skills)

    assert valid == ["file_manager"]
```

- [ ] **Step 2: Run integration tests and verify they fail**

Run: `pytest tests/unit/test_rbac_resource_permissions.py -q`

Expected: FAIL because `SkillManager.list_skills_for_role()` does not exist and `ExpertAgentValidator.validate_skills_from_profile()` does not accept `all_skills`.

- [ ] **Step 3: Implement role-aware Skill manager methods**

In `harness/skill/manager.py`, add:

```python
    def get_skill(self, skill_name: str):
        manifest = self.get_manifest()
        for skill in manifest.skills:
            if skill.name == skill_name:
                return skill
        return None

    def list_skills_for_role(self, role) -> list:
        from runtime.context_schema import UserRole
        from harness.security.rbac import role_allows_skill

        role_enum = role if isinstance(role, UserRole) else UserRole(role)
        return [skill for skill in self.list_skills() if role_allows_skill(role_enum, skill)]
```

- [ ] **Step 4: Update expert Skill validation to use helper**

In `harness/expert/validator.py`, change `validate_skills_from_profile` to accept optional SkillInfo list:

```python
    @staticmethod
    def validate_skills_from_profile(role: str, skills: list[str], all_skills: list[SkillInfo] | None = None) -> list[str]:
        role_enum = UserRole(role)
        skill_map = {s.name: s for s in (all_skills or [])}
        valid = []
        for skill_name in skills:
            skill_obj = skill_map.get(skill_name) or ExpertAgentValidator._get_skill_info(skill_name)
            if skill_obj is None:
                valid.append(skill_name)
                continue
            from harness.security.rbac import role_allows_skill
            if role_allows_skill(role_enum, skill_obj):
                valid.append(skill_name)

        rejected = [s for s in skills if s not in valid]
        if rejected:
            from structlog import get_logger
            get_logger().warning("skill_privilege_escalation_blocked", role=role, rejected=rejected)
        return valid
```

- [ ] **Step 5: Run Skill integration tests**

Run: `pytest tests/unit/test_rbac_resource_permissions.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Skill integration changes**

```bash
git add harness/skill/manager.py harness/expert/validator.py tests/unit/test_rbac_resource_permissions.py
git commit -m "feat: enforce precise skill role permissions"
```

---

### Task 3: Backend RBAC Resource API

**Files:**
- Modify: `gateway/server.py`
- Test: `tests/unit/test_rbac_resource_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/unit/test_rbac_resource_api.py`:

```python
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from gateway import server
from harness.security import rbac
from harness.skill.types import SkillAccess, SkillCategory, SkillInfo, SkillManifest
from runtime.context_schema import UserContext, UserRole


def make_skill(name: str, access: SkillAccess = SkillAccess.REPORT) -> SkillInfo:
    return SkillInfo(
        name=name,
        description=f"{name} desc",
        category=SkillCategory.FILE_MANAGER,
        access=access,
        location=f"/tmp/{name}/SKILL.md",
    )


class FakeSkillManager:
    def __init__(self):
        self.skills = [
            make_skill("file_manager", SkillAccess.REPORT),
            make_skill("database_query", SkillAccess.ENTERPRISE),
        ]

    def list_skills(self):
        return self.skills

    def get_manifest(self, user_skill_access=None, skill_names=None):
        return SkillManifest(skills=self.skills)


class FakeMCPManager:
    def list_servers(self):
        from harness.mcp.types import MCPServerConfig
        return [MCPServerConfig(name="filesystem", enabled=True), MCPServerConfig(name="github", enabled=False)]

    def get_server(self, name):
        from harness.mcp.types import MCPServerConfig
        if name in {"filesystem", "github"}:
            return MCPServerConfig(name=name, enabled=True)
        return None

    def get_all_tools_info(self):
        return []


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = tmp_path / "rbac.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "rbac": {
                    "roles": {
                        "admin": {"tools": [], "mcp_tools": ["*"], "skill_access": "all", "skills": ["*"]},
                        "manager": {"tools": [], "mcp_tools": [], "skill_access": "enterprise"},
                        "operator": {"tools": [], "mcp_tools": ["filesystem:*"], "skill_access": "production"},
                        "viewer": {"tools": [], "mcp_tools": [], "skill_access": "report"},
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rbac, "DEFAULT_RBAC_CONFIG_PATH", str(cfg))
    rbac.clear_rbac_caches()
    monkeypatch.setattr(server, "skill_manager", FakeSkillManager())
    monkeypatch.setattr(server, "mcp_manager", FakeMCPManager())
    monkeypatch.setattr(
        server,
        "require_admin",
        lambda authorization=None: UserContext(user_id="admin", role=UserRole.ADMIN),
    )
    return TestClient(server.app), cfg


def test_get_rbac_resources_returns_roles_for_skills_and_mcp(client):
    test_client, _ = client

    res = test_client.get("/api/rbac/resources", headers={"Authorization": "Bearer token"})

    assert res.status_code == 200
    body = res.json()
    assert body["roles"] == ["admin", "manager", "operator", "viewer"]
    file_skill = next(s for s in body["skills"] if s["name"] == "file_manager")
    assert "operator" in file_skill["roles"]
    filesystem = next(s for s in body["mcp_servers"] if s["name"] == "filesystem")
    assert filesystem["roles"] == ["admin", "operator"]


def test_put_skill_roles_updates_rbac_yaml(client):
    test_client, cfg = client

    res = test_client.put(
        "/api/rbac/skills/file_manager/roles",
        json={"roles": ["admin", "viewer"]},
        headers={"Authorization": "Bearer token"},
    )

    assert res.status_code == 200
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    roles = saved["rbac"]["roles"]
    assert "file_manager" in roles["admin"]["skills"]
    assert "file_manager" in roles["viewer"]["skills"]
    assert "file_manager" not in roles["operator"]["skills"]


def test_put_mcp_server_roles_updates_server_wildcards(client):
    test_client, cfg = client

    res = test_client.put(
        "/api/rbac/mcp-servers/github/roles",
        json={"roles": ["manager"]},
        headers={"Authorization": "Bearer token"},
    )

    assert res.status_code == 200
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert "github:*" in saved["rbac"]["roles"]["manager"]["mcp_tools"]
    assert "github:*" not in saved["rbac"]["roles"]["operator"]["mcp_tools"]
```

- [ ] **Step 2: Run API tests and verify they fail**

Run: `pytest tests/unit/test_rbac_resource_api.py -q`

Expected: FAIL with 404 responses because the RBAC resource endpoints do not exist.

- [ ] **Step 3: Add request models and helpers to `gateway/server.py`**

Near other request models, add:

```python
class ResourceRolesRequest(BaseModel):
    roles: list[str]
```

Add helper:

```python
def _role_values() -> list[str]:
    return [role.value for role in UserRole]
```

- [ ] **Step 4: Add RBAC resource endpoints**

Add this section before the expert-agent CRUD API in `gateway/server.py`:

```python
@app.get("/api/rbac/resources")
async def get_rbac_resources(authorization: str = Header(default=None)):
    require_admin(authorization)
    from harness.security.rbac import roles_for_skill, roles_for_mcp_server

    skills = skill_manager.list_skills()
    servers = mcp_manager.list_servers()

    return {
        "roles": _role_values(),
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "access": skill.access.value,
                "roles": [role.value for role in roles_for_skill(skill.name, skills)],
            }
            for skill in skills
        ],
        "mcp_servers": [
            {
                "name": server_config.name,
                "enabled": server_config.enabled,
                "roles": [role.value for role in roles_for_mcp_server(server_config.name)],
            }
            for server_config in servers
        ],
    }


@app.put("/api/rbac/skills/{skill_name}/roles")
async def update_skill_roles(skill_name: str, req: ResourceRolesRequest, authorization: str = Header(default=None)):
    require_admin(authorization)
    from harness.security.rbac import normalize_roles, set_skill_roles

    all_skills = skill_manager.list_skills()
    if not any(skill.name == skill_name for skill in all_skills):
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    try:
        roles = normalize_roles(req.roles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    set_skill_roles(skill_name, roles, all_skills)
    return {"name": skill_name, "roles": [role.value for role in roles]}


@app.put("/api/rbac/mcp-servers/{server_name}/roles")
async def update_mcp_server_roles(server_name: str, req: ResourceRolesRequest, authorization: str = Header(default=None)):
    require_admin(authorization)
    from harness.security.rbac import normalize_roles, set_mcp_server_roles

    if mcp_manager.get_server(server_name) is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    try:
        roles = normalize_roles(req.roles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    set_mcp_server_roles(server_name, roles)
    return {"name": server_name, "roles": [role.value for role in roles]}
```

- [ ] **Step 5: Update role-filtered endpoints to use helper functions**

In `/api/roles/{role}/skills`, replace the local `SkillAccess.max_for_role` calculation with:

```python
from harness.security.rbac import role_allows_skill

skill_list = skill_manager.list_skills()
result = []
for skill in skill_list:
    allowed = role_allows_skill(target_role, skill)
    result.append({
        "name": skill.name,
        "description": skill.description,
        "access": skill.access.value,
        "allowed": allowed,
    })
```

In `/api/roles/{role}/mcp-tools`, keep existing tool matching but ensure it still calls `ExpertAgentValidator.get_role_mcp_tools(target_role.value)`.

- [ ] **Step 6: Run API tests and existing RBAC tests**

Run:

```bash
pytest tests/unit/test_rbac_resource_api.py tests/unit/test_rbac_resource_permissions.py tests/unit/test_rbac.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit API changes**

```bash
git add gateway/server.py tests/unit/test_rbac_resource_api.py
git commit -m "feat: add rbac resource permission api"
```

---

### Task 4: Frontend RBAC Client and Store State

**Files:**
- Modify: `web/src/types/api.ts`
- Create: `web/src/api/rbac.ts`
- Modify: `web/src/store/adminStore.ts`
- Modify: `web/src/store/mcpStore.ts`
- Test: `web/src/api/rbac.test.ts`

- [ ] **Step 1: Write failing frontend API test**

Create `web/src/api/rbac.test.ts`:

```typescript
import { describe, expect, test, vi, beforeEach } from 'vitest';
import client from './client';
import { getRbacResources, updateMCPServerRoles, updateSkillRoles } from './rbac';

vi.mock('./client', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

describe('rbac api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('loads rbac resources', async () => {
    vi.mocked(client.get).mockResolvedValueOnce({ data: { roles: ['admin'], skills: [], mcp_servers: [] } });

    const res = await getRbacResources();

    expect(client.get).toHaveBeenCalledWith('/api/rbac/resources');
    expect(res.roles).toEqual(['admin']);
  });

  test('updates skill roles', async () => {
    vi.mocked(client.put).mockResolvedValueOnce({ data: { name: 'file_manager', roles: ['admin'] } });

    await updateSkillRoles('file_manager', ['admin']);

    expect(client.put).toHaveBeenCalledWith('/api/rbac/skills/file_manager/roles', { roles: ['admin'] });
  });

  test('updates mcp server roles', async () => {
    vi.mocked(client.put).mockResolvedValueOnce({ data: { name: 'filesystem', roles: ['operator'] } });

    await updateMCPServerRoles('filesystem', ['operator']);

    expect(client.put).toHaveBeenCalledWith('/api/rbac/mcp-servers/filesystem/roles', { roles: ['operator'] });
  });
});
```

- [ ] **Step 2: Run frontend API test and verify it fails**

Run: `npm test -- rbac.test.ts`

Expected: FAIL because `web/src/api/rbac.ts` does not exist.

- [ ] **Step 3: Add RBAC frontend types**

In `web/src/types/api.ts`, add:

```typescript
export interface RbacSkillResource {
  name: string;
  description: string;
  access: string;
  roles: UserRole[];
}

export interface RbacMCPServerResource {
  name: string;
  enabled: boolean;
  roles: UserRole[];
}

export interface RbacResources {
  roles: UserRole[];
  skills: RbacSkillResource[];
  mcp_servers: RbacMCPServerResource[];
}

export interface ResourceRolesUpdate {
  roles: UserRole[];
}
```

- [ ] **Step 4: Create RBAC API client**

Create `web/src/api/rbac.ts`:

```typescript
import client from './client';
import type { RbacResources, ResourceRolesUpdate, UserRole } from '../types/api';

export async function getRbacResources(): Promise<RbacResources> {
  const res = await client.get('/api/rbac/resources');
  return res.data;
}

export async function updateSkillRoles(skillName: string, roles: UserRole[]): Promise<{ name: string; roles: UserRole[] }> {
  const req: ResourceRolesUpdate = { roles };
  const res = await client.put(`/api/rbac/skills/${skillName}/roles`, req);
  return res.data;
}

export async function updateMCPServerRoles(serverName: string, roles: UserRole[]): Promise<{ name: string; roles: UserRole[] }> {
  const req: ResourceRolesUpdate = { roles };
  const res = await client.put(`/api/rbac/mcp-servers/${serverName}/roles`, req);
  return res.data;
}
```

- [ ] **Step 5: Add store state for RBAC resources**

In `web/src/store/adminStore.ts`, add imports and state:

```typescript
import type { RbacResources, UserRole } from '../types/api';
import * as rbacApi from '../api/rbac';
```

Add to `AdminState`:

```typescript
  rbacResources: RbacResources | null;
  loadRbacResources: () => Promise<void>;
  updateSkillRoles: (skillName: string, roles: UserRole[]) => Promise<void>;
```

Add default state and implementations:

```typescript
  rbacResources: null,

  loadRbacResources: async () => {
    const resources = await rbacApi.getRbacResources();
    set({ rbacResources: resources });
  },

  updateSkillRoles: async (skillName, roles) => {
    await rbacApi.updateSkillRoles(skillName, roles);
    const resources = await rbacApi.getRbacResources();
    set({ rbacResources: resources });
  },
```

In `web/src/store/mcpStore.ts`, add either equivalent state or plan to call `rbacApi` directly from `MCPServerManager`. Prefer direct page calls for MCP to keep store focused on MCP connection state.

- [ ] **Step 6: Run API test**

Run: `npm test -- rbac.test.ts`

Expected: PASS.

- [ ] **Step 7: Commit frontend API changes**

```bash
git add web/src/types/api.ts web/src/api/rbac.ts web/src/api/rbac.test.ts web/src/store/adminStore.ts
git commit -m "feat: add frontend rbac permissions api"
```

---

### Task 5: Skill Management Role UI

**Files:**
- Modify: `web/src/components/SkillManager.tsx`
- Test: `web/src/components/SkillManager.test.tsx`

- [ ] **Step 1: Write failing SkillManager UI test**

Create `web/src/components/SkillManager.test.tsx`:

```typescript
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SkillManager from './SkillManager';
import { useAdminStore } from '../store/adminStore';

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

describe('SkillManager permissions', () => {
  beforeEach(() => {
    useAdminStore.setState({
      skills: [{ name: 'file_manager', description: 'Files', category: 'file_manager', access: 'report' }],
      rbacResources: {
        roles: ['admin', 'manager', 'operator', 'viewer'],
        skills: [{ name: 'file_manager', description: 'Files', access: 'report', roles: ['admin'] }],
        mcp_servers: [],
      },
      loadSkills: vi.fn().mockResolvedValue(undefined),
      loadRbacResources: vi.fn().mockResolvedValue(undefined),
      updateSkillRoles: vi.fn().mockResolvedValue(undefined),
    } as any);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  test('renders role checkboxes and saves selected roles', async () => {
    render(<SkillManager />);

    expect(await screen.findByText('file_manager')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('operator'));
    fireEvent.click(screen.getByRole('button', { name: '保存角色权限' }));

    await waitFor(() => {
      expect(useAdminStore.getState().updateSkillRoles).toHaveBeenCalledWith('file_manager', ['admin', 'operator']);
    });
  });
});
```

- [ ] **Step 2: Run SkillManager UI test and verify it fails**

Run: `npm test -- SkillManager.test.tsx`

Expected: FAIL because SkillManager does not render role checkboxes or a save permission button.

- [ ] **Step 3: Update SkillManager to load RBAC resources**

In `web/src/components/SkillManager.tsx`, update `useEffect`:

```typescript
  useEffect(() => {
    store.loadSkills();
    store.loadRbacResources();
  }, []);
```

Add helper:

```typescript
  const getSkillRoles = (skillName: string) => (
    store.rbacResources?.skills.find((s) => s.name === skillName)?.roles || []
  );
```

- [ ] **Step 4: Add role checkbox group and save handler**

Import `Checkbox` and `UserRole`:

```typescript
import { Button, Card, Checkbox, message, Space, List, Spin, Upload } from 'antd';
import type { UserRole } from '../types/api';
```

Add handler:

```typescript
  const handleSaveRoles = async (skillName: string, roles: UserRole[]) => {
    setLoading(`roles:${skillName}`);
    try {
      await store.updateSkillRoles(skillName, roles);
      message.success('角色权限已保存');
    } catch {
      message.error('角色权限保存失败');
    } finally {
      setLoading('');
    }
  };
```

Inside each Skill card, add:

```tsx
              <div style={{ marginBottom: 12 }}>
                <Checkbox.Group
                  options={(store.rbacResources?.roles || []).map((role) => ({ label: role, value: role }))}
                  value={getSkillRoles(skill.name)}
                  onChange={(vals) => {
                    const roles = vals as UserRole[];
                    useAdminStore.setState((state) => ({
                      rbacResources: state.rbacResources
                        ? {
                          ...state.rbacResources,
                          skills: state.rbacResources.skills.map((item) => (
                            item.name === skill.name ? { ...item, roles } : item
                          )),
                        }
                        : state.rbacResources,
                    }));
                  }}
                />
              </div>
              <Button
                size="small"
                onClick={() => handleSaveRoles(skill.name, getSkillRoles(skill.name))}
                loading={loading === `roles:${skill.name}`}
              >
                保存角色权限
              </Button>
```

Keep the existing GEPA button after this block.

- [ ] **Step 5: Run SkillManager UI test**

Run: `npm test -- SkillManager.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit Skill UI changes**

```bash
git add web/src/components/SkillManager.tsx web/src/components/SkillManager.test.tsx
git commit -m "feat: configure skill role permissions in ui"
```

---

### Task 6: MCP Service Role UI

**Files:**
- Modify: `web/src/pages/MCPServerManager.tsx`
- Test: `web/src/pages/MCPServerManager.test.tsx`

- [ ] **Step 1: Write failing MCP UI test**

Create `web/src/pages/MCPServerManager.test.tsx`:

```typescript
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import MCPServerManager from './MCPServerManager';
import { useMCPStore } from '../store/mcpStore';
import * as mcpApi from '../api/mcp';
import * as rbacApi from '../api/rbac';

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

vi.mock('../api/mcp');
vi.mock('../api/rbac');

describe('MCPServerManager permissions', () => {
  beforeEach(() => {
    useMCPStore.setState({
      servers: [{ name: 'filesystem', transport: 'stdio', command: 'npx', args: [], url: '', enabled: true, env: {} }],
      tools: [],
      loading: false,
      loadServers: vi.fn().mockResolvedValue(undefined),
      updateServer: vi.fn().mockResolvedValue(undefined),
    } as any);
    vi.mocked(mcpApi.getMCPServer).mockResolvedValue({
      config: { name: 'filesystem', transport: 'stdio', command: 'npx', args: [], url: '', enabled: true, env: {} },
      tools: [],
    });
    vi.mocked(rbacApi.getRbacResources).mockResolvedValue({
      roles: ['admin', 'manager', 'operator', 'viewer'],
      skills: [],
      mcp_servers: [{ name: 'filesystem', enabled: true, roles: ['admin'] }],
    });
    vi.mocked(rbacApi.updateMCPServerRoles).mockResolvedValue({ name: 'filesystem', roles: ['admin', 'operator'] });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  test('renders and saves service-level roles', async () => {
    render(<MCPServerManager />);

    fireEvent.click(await screen.findByText('filesystem'));
    fireEvent.click(await screen.findByLabelText('operator'));
    fireEvent.click(screen.getByRole('button', { name: '保存角色权限' }));

    await waitFor(() => {
      expect(rbacApi.updateMCPServerRoles).toHaveBeenCalledWith('filesystem', ['admin', 'operator']);
    });
  });
});
```

- [ ] **Step 2: Run MCP UI test and verify it fails**

Run: `npm test -- MCPServerManager.test.tsx`

Expected: FAIL because MCPServerManager does not load RBAC resources or render role checkboxes.

- [ ] **Step 3: Update MCPServerManager imports and state**

In `web/src/pages/MCPServerManager.tsx`, import:

```typescript
import type { MCPServerConfig, MCPToolInfo, RbacResources, UserRole } from '../types/api';
import * as rbacApi from '../api/rbac';
```

Add state:

```typescript
  const [rbacResources, setRbacResources] = useState<RbacResources | null>(null);
  const [savingRoles, setSavingRoles] = useState(false);
```

Update `useEffect`:

```typescript
  useEffect(() => {
    store.loadServers();
    rbacApi.getRbacResources().then(setRbacResources).catch(() => message.error('加载角色权限失败'));
  }, []);
```

- [ ] **Step 4: Add MCP role helper and save handler**

Add:

```typescript
  const getServerRoles = useCallback((serverName: string): UserRole[] => (
    rbacResources?.mcp_servers.find((s) => s.name === serverName)?.roles || []
  ), [rbacResources]);

  const setServerRoles = useCallback((serverName: string, roles: UserRole[]) => {
    setRbacResources((prev) => prev
      ? {
        ...prev,
        mcp_servers: prev.mcp_servers.map((s) => (
          s.name === serverName ? { ...s, roles } : s
        )),
      }
      : prev);
  }, []);

  const handleSaveRoles = useCallback(async () => {
    if (!selectedServer) return;
    setSavingRoles(true);
    try {
      await rbacApi.updateMCPServerRoles(selectedServer, getServerRoles(selectedServer));
      const resources = await rbacApi.getRbacResources();
      setRbacResources(resources);
      message.success('角色权限已保存');
    } catch {
      message.error('角色权限保存失败');
    } finally {
      setSavingRoles(false);
    }
  }, [selectedServer, getServerRoles]);
```

- [ ] **Step 5: Add role checkbox UI to MCP form**

Inside the form for selected server, after enabled switch row, add:

```tsx
              {selectedServer && (
                <Form.Item label="允许角色">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Checkbox.Group
                      options={(rbacResources?.roles || []).map((role) => ({ label: role, value: role }))}
                      value={getServerRoles(selectedServer)}
                      onChange={(vals) => setServerRoles(selectedServer, vals as UserRole[])}
                    />
                    <Button size="small" onClick={handleSaveRoles} loading={savingRoles}>
                      保存角色权限
                    </Button>
                  </Space>
                </Form.Item>
              )}
```

Add `Checkbox` to the Ant Design import list.

- [ ] **Step 6: Run MCP UI test**

Run: `npm test -- MCPServerManager.test.tsx`

Expected: PASS.

- [ ] **Step 7: Commit MCP UI changes**

```bash
git add web/src/pages/MCPServerManager.tsx web/src/pages/MCPServerManager.test.tsx
git commit -m "feat: configure mcp service role permissions in ui"
```

---

### Task 7: End-to-End Verification

**Files:**
- Modify only if verification reveals a defect.

- [ ] **Step 1: Run backend role and expert tests**

Run:

```bash
pytest tests/unit/test_rbac.py tests/unit/test_rbac_resource_permissions.py tests/unit/test_rbac_resource_api.py tests/unit/test_expert.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend permission tests**

Run:

```bash
npm test -- App.test.tsx rbac.test.ts SkillManager.test.tsx MCPServerManager.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
npm run build
```

Expected: exit code 0. Existing Vite chunk-size warnings are acceptable.

- [ ] **Step 4: Inspect diff for generated noise**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intentional source, test, and config changes are present. Do not commit local logs, `web/dist`, `web/node_modules`, or unrelated generated files.

- [ ] **Step 5: Final commit if any verification fixes were needed**

If Task 7 required fixes, commit them:

```bash
git add harness/security/rbac.py harness/skill/manager.py harness/expert/validator.py gateway/server.py tests/unit/test_rbac_resource_permissions.py tests/unit/test_rbac_resource_api.py web/src/types/api.ts web/src/api/rbac.ts web/src/api/rbac.test.ts web/src/store/adminStore.ts web/src/components/SkillManager.tsx web/src/components/SkillManager.test.tsx web/src/pages/MCPServerManager.tsx web/src/pages/MCPServerManager.test.tsx
git commit -m "fix: stabilize resource permission tests"
```

Expected: working tree has only intended tracked changes or is clean.

---

## Self-Review Notes

- Spec coverage: backend helpers, RBAC YAML writes, API endpoints, Skill UI, MCP service UI, expert-agent role-filter reuse, and verification are covered by Tasks 1 through 7.
- Scope: stays within resource-level permissions; no per-tool MCP UI or role taxonomy changes.
- Type consistency: frontend uses `UserRole`, `RbacResources`, `RbacSkillResource`, and `RbacMCPServerResource` from `web/src/types/api.ts`; backend uses `UserRole` and existing `SkillInfo`/`MCPServerConfig`.
- TDD path: each implementation task begins with a failing test and a command to verify the failure before production code.
