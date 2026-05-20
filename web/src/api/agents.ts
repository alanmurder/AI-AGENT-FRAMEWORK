import client from './client';
import type { AgentProfile, TeamConfig, TaskItem } from '../types/agent';

export interface AgentsResponse {
  manifest: Record<string, unknown>;
  agents: AgentProfile[];
}

export interface TeamsResponse {
  teams: TeamConfig[];
}

export async function listAgents(): Promise<AgentsResponse> {
  const res = await client.get<AgentsResponse>('/api/agents');
  return res.data;
}

export async function listTeams(): Promise<TeamsResponse> {
  const res = await client.get<TeamsResponse>('/api/teams');
  return res.data;
}

export async function getAgentTasks(agentName: string, userId?: string): Promise<{ board_id: string; tasks: TaskItem[] }> {
  const res = await client.get(`/api/agents/${agentName}/tasks`, { params: { user_id: userId } });
  return res.data;
}