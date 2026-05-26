// @vitest-environment node

import { beforeEach, describe, expect, it, type Mock, vi } from 'vitest';
import client from './client';
import { getRbacResources, updateMCPServerRoles, updateSkillRoles } from './rbac';
import type { RbacResources } from '../types/api';
import { useAdminStore } from '../store/adminStore';

vi.mock('./client', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

const mockedClient = client as unknown as {
  get: Mock;
  put: Mock;
};

describe('rbac api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('gets RBAC resources from the resources endpoint', async () => {
    const data: RbacResources = {
      roles: ['admin', 'operator'],
      skills: [
        {
          name: 'file_manager',
          description: 'Manage files',
          access: 'protected',
          roles: ['admin'],
        },
      ],
      mcp_servers: [
        {
          name: 'filesystem',
          enabled: true,
          roles: ['operator'],
        },
      ],
    };
    mockedClient.get.mockResolvedValueOnce({ data });

    await expect(getRbacResources()).resolves.toEqual(data);

    expect(mockedClient.get).toHaveBeenCalledWith('/api/rbac/resources');
  });

  it('updates skill roles', async () => {
    const data = { name: 'file_manager', roles: ['admin'] };
    mockedClient.put.mockResolvedValueOnce({ data });

    await expect(updateSkillRoles('file_manager', ['admin'])).resolves.toEqual(data);

    expect(mockedClient.put).toHaveBeenCalledWith('/api/rbac/skills/file_manager/roles', {
      roles: ['admin'],
    });
  });

  it('encodes skill names when updating skill roles', async () => {
    const data = { name: 'folder/skill', roles: ['admin'] };
    mockedClient.put.mockResolvedValueOnce({ data });

    await updateSkillRoles('folder/skill', ['admin']);

    expect(mockedClient.put).toHaveBeenCalledWith('/api/rbac/skills/folder%2Fskill/roles', {
      roles: ['admin'],
    });
  });

  it('updates MCP server roles', async () => {
    const data = { name: 'filesystem', roles: ['operator'] };
    mockedClient.put.mockResolvedValueOnce({ data });

    await expect(updateMCPServerRoles('filesystem', ['operator'])).resolves.toEqual(data);

    expect(mockedClient.put).toHaveBeenCalledWith('/api/rbac/mcp-servers/filesystem/roles', {
      roles: ['operator'],
    });
  });

  it('encodes MCP server names when updating server roles', async () => {
    const data = { name: 'filesystem/prod', roles: ['operator'] };
    mockedClient.put.mockResolvedValueOnce({ data });

    await updateMCPServerRoles('filesystem/prod', ['operator']);

    expect(mockedClient.put).toHaveBeenCalledWith('/api/rbac/mcp-servers/filesystem%2Fprod/roles', {
      roles: ['operator'],
    });
  });

  it('refreshes admin store resources after role updates', async () => {
    const initial: RbacResources = { roles: ['admin'], skills: [], mcp_servers: [] };
    const afterSkill: RbacResources = {
      roles: ['admin'],
      skills: [{ name: 'file_manager', description: 'Files', access: 'report', roles: ['admin'] }],
      mcp_servers: [],
    };
    const afterMCP: RbacResources = {
      roles: ['admin'],
      skills: [],
      mcp_servers: [{ name: 'filesystem', enabled: true, roles: ['admin'] }],
    };
    mockedClient.get
      .mockResolvedValueOnce({ data: initial })
      .mockResolvedValueOnce({ data: afterSkill })
      .mockResolvedValueOnce({ data: afterMCP });
    mockedClient.put.mockResolvedValue({ data: { name: 'resource', roles: ['admin'] } });
    useAdminStore.setState({ rbacResources: null });

    await useAdminStore.getState().loadRbacResources();
    expect(useAdminStore.getState().rbacResources).toEqual(initial);

    await useAdminStore.getState().updateSkillRoles('file_manager', ['admin']);
    expect(mockedClient.put).toHaveBeenCalledWith('/api/rbac/skills/file_manager/roles', {
      roles: ['admin'],
    });
    expect(useAdminStore.getState().rbacResources).toEqual(afterSkill);

    await useAdminStore.getState().updateMCPServerRoles('filesystem', ['admin']);
    expect(mockedClient.put).toHaveBeenCalledWith('/api/rbac/mcp-servers/filesystem/roles', {
      roles: ['admin'],
    });
    expect(useAdminStore.getState().rbacResources).toEqual(afterMCP);
  });
});
