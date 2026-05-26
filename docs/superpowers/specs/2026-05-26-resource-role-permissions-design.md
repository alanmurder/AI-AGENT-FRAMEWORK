# Resource Role Permissions Design

## Goal

Allow admins to configure which user roles can use each Skill and MCP service from the existing resource management pages. The UI should feel resource-centric: Skill permissions live in Skill management, and MCP permissions live in MCP service management.

The backend remains the authority. `config/rbac.yaml` is the single source of truth for effective permissions, so runtime filtering, expert-agent creation, and management pages all read the same permission model.

## Existing Behavior

The system already has role-based access control in `config/rbac.yaml`.

- Generic tools are listed under each role's `tools`.
- MCP access is listed under each role's `mcp_tools`.
- Skill visibility currently uses each role's `skill_access` level.
- Expert-agent creation already asks the backend for role-filtered Skills and MCP tools.
- Runtime agent creation already filters MCP tools by role and injects role-filtered Skill manifests.

The missing piece is a resource-level UI and API for editing these permissions.

## Data Model

Continue using `config/rbac.yaml` as the effective permission source.

Skill permissions gain an optional precise allow-list per role:

```yaml
rbac:
  roles:
    operator:
      skill_access: production
      skills:
        - file_manager
        - schedule_manager
```

Skill permission rules:

- If a role has `skills: ["*"]`, the role can use all Skills.
- If a role has a `skills` field, including an empty list, that list is authoritative for Skill access.
- If a role has no `skills` field, fall back to the current `skill_access` hierarchy.
- Existing `skill_access` stays in the file for compatibility and for coarse defaults.

MCP permissions continue using the existing `mcp_tools` format:

```yaml
rbac:
  roles:
    operator:
      mcp_tools:
        - filesystem:*
```

MCP permission rules:

- `*` allows all MCP tools.
- `server:*` allows every tool exposed by a server.
- `server:tool` remains supported for compatibility, but the UI in this feature writes service-level `server:*` entries only.

## Backend API

All write endpoints require admin authorization.

`GET /api/rbac/resources`

Returns roles, Skills, MCP servers, and current role assignments for each resource. This endpoint lets Skill and MCP pages load permission state without duplicating permission logic in the frontend.

Response shape:

```json
{
  "roles": ["admin", "manager", "operator", "viewer"],
  "skills": [
    {
      "name": "file_manager",
      "description": "Manage files",
      "access": "production",
      "roles": ["admin", "manager", "operator"]
    }
  ],
  "mcp_servers": [
    {
      "name": "filesystem",
      "enabled": true,
      "roles": ["admin", "operator"]
    }
  ]
}
```

`PUT /api/rbac/skills/{skill_name}/roles`

Request:

```json
{ "roles": ["admin", "manager"] }
```

Behavior:

- Validate the Skill exists.
- Validate all roles are known roles.
- If no role has a precise `skills` field yet, materialize current effective Skill permissions into every role's `skills` list before applying the update.
- Remove the Skill from every role's precise `skills` list.
- Add the Skill to each requested role's `skills` list.
- Preserve all unrelated RBAC fields.

`PUT /api/rbac/mcp-servers/{server_name}/roles`

Request:

```json
{ "roles": ["admin", "operator"] }
```

Behavior:

- Validate the MCP server exists.
- Validate all roles are known roles.
- Remove `server:*` and any `server:tool` entries for that server from every role's `mcp_tools`.
- Add `server:*` to each requested role's `mcp_tools`.
- Keep unrelated MCP entries for other servers.
- Preserve all unrelated RBAC fields.

## Permission Calculation

Add shared helper functions in the RBAC layer so all callers use one implementation:

- `role_allows_skill(role, skill)`
- `roles_for_skill(skill_name)`
- `set_skill_roles(skill_name, roles)`
- `roles_for_mcp_server(server_name)`
- `set_mcp_server_roles(server_name, roles)`

The existing expert-agent validation and role-filtered listing endpoints should call these helpers instead of reimplementing Skill or MCP checks locally.

Runtime behavior:

- Generic agents continue to receive only role-allowed MCP tools.
- Skill manifest injection continues to include only role-allowed Skills.
- Expert agents continue to restrict configured Skills and MCP tools by their configured role.

## Frontend UX

Skill management:

- Each Skill card shows an "Allowed roles" checkbox group.
- The group includes `admin`, `manager`, `operator`, and `viewer`.
- Saving the checkbox group calls `PUT /api/rbac/skills/{skill_name}/roles`.
- On success, refresh the RBAC resource state.
- Empty role selection is allowed and means no role can use that Skill once precise Skill permissions have been materialized. Admins should use it deliberately.

MCP service management:

- The MCP server form shows an "Allowed roles" checkbox group.
- Permissions are service-level. Selecting a role grants `server:*`.
- Saving the MCP server can save the server config and permission update in sequence, or permissions can have a separate save action. The implementation should avoid a UI state where server changes appear saved but permission changes silently fail.
- The discovered tool list remains informational.

Expert-agent management:

- No major UI change is needed.
- The existing role-specific Skill and MCP selectors continue to use backend role-filtered endpoints.
- Once resource permissions are changed, expert-agent creation automatically reflects the new allowed resources.

## Error Handling

- Unknown role returns `400`.
- Unknown Skill or MCP server returns `404`.
- Non-admin writes return `403`.
- RBAC YAML parse or write failures return `500` and do not update in-memory caches.
- After a successful RBAC write, clear RBAC caches so subsequent requests and runtime agent creation see the new permissions.

## Testing

Backend tests:

- A role with `skills` can only access those Skill names.
- A role without `skills` still falls back to `skill_access`.
- `skills: ["*"]` allows all Skills.
- Updating Skill roles edits only role `skills` lists and preserves unrelated RBAC fields.
- Updating MCP server roles writes `server:*` to requested roles.
- MCP runtime filtering still recognizes `server:*`.
- Expert-agent validation rejects Skills and MCP services not allowed for the selected role.

Frontend tests:

- Skill management renders role checkboxes for each Skill.
- Saving Skill roles calls the RBAC endpoint and refreshes state.
- MCP server management renders service-level role checkboxes.
- Saving MCP roles calls the RBAC endpoint and refreshes state.

## Non-Goals

- No per-tool MCP UI in this feature.
- No new role types.
- No migration away from `config/rbac.yaml`.
- No separate permission store in `data/`.
- No redesign of expert-agent creation.

## Rollout Notes

Existing `skill_access` and `mcp_tools` configurations remain valid. The feature can be adopted incrementally:

1. Existing roles continue working with current `skill_access` and `mcp_tools`.
2. Admins can start setting exact Skill roles from the Skill page.
3. Admins can set MCP service roles from the MCP page.
4. Once precise Skill lists are present, those lists become the effective Skill permission source for that role.
