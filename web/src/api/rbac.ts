import client from './client';
import type { RbacResources, ResourceRolesUpdate, UserRole } from '../types/api';

interface ResourceRolesResponse {
  name: string;
  roles: UserRole[];
}

export async function getRbacResources(): Promise<RbacResources> {
  const res = await client.get('/api/rbac/resources');
  return res.data;
}

export async function updateSkillRoles(skillName: string, roles: UserRole[]): Promise<ResourceRolesResponse> {
  const req: ResourceRolesUpdate = { roles };
  const res = await client.put(`/api/rbac/skills/${skillName}/roles`, req);
  return res.data;
}

export async function updateMCPServerRoles(serverName: string, roles: UserRole[]): Promise<ResourceRolesResponse> {
  const req: ResourceRolesUpdate = { roles };
  const res = await client.put(`/api/rbac/mcp-servers/${serverName}/roles`, req);
  return res.data;
}
