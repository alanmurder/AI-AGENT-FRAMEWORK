import client from './client';
import type { AgentProfile } from '../types/agent';
import type { CreateAgentRequest, UpdateAgentRequest, RoleSkillInfo, RoleMCPToolInfo, TestConnectionResult } from '../types/api';

export async function listManageableAgents(): Promise<{ agents: AgentProfile[] }> {
  const res = await client.get('/api/agents/manage');
  return res.data;
}

export async function getAgent(name: string): Promise<{ agent: AgentProfile; soul_content: string }> {
  const res = await client.get(`/api/agents/manage/${name}`);
  return res.data;
}

export async function createAgent(req: CreateAgentRequest): Promise<{ message: string; agent: AgentProfile }> {
  const res = await client.post('/api/agents/manage', req);
  return res.data;
}

export async function updateAgent(name: string, req: UpdateAgentRequest): Promise<{ message: string; agent: AgentProfile }> {
  const res = await client.put(`/api/agents/manage/${name}`, req);
  return res.data;
}

export async function deleteAgent(name: string): Promise<{ deleted: string }> {
  const res = await client.delete(`/api/agents/manage/${name}`);
  return res.data;
}

export async function getRoleSkills(role: string): Promise<{ role: string; skill_access: string; skills: RoleSkillInfo[] }> {
  const res = await client.get(`/api/roles/${role}/skills`);
  return res.data;
}

export async function getRoleMCPTools(role: string): Promise<{ role: string; mcp_tools: RoleMCPToolInfo[] }> {
  const res = await client.get(`/api/roles/${role}/mcp-tools`);
  return res.data;
}

export async function testAgentConnection(name: string): Promise<TestConnectionResult> {
  const res = await client.post(`/api/agents/manage/${name}/test-connection`);
  return res.data;
}
