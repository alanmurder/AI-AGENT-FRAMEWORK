import { create } from 'zustand';
import type { AgentProfile } from '../types/agent';
import type { CreateAgentRequest, UpdateAgentRequest, RoleSkillInfo, RoleMCPToolInfo } from '../types/api';
import * as expertApi from '../api/expert-agents';

interface ExpertAgentState {
  agents: AgentProfile[];
  roleSkills: RoleSkillInfo[];
  roleMCPTools: RoleMCPToolInfo[];
  loading: boolean;

  loadAgents: () => Promise<void>;
  loadRoleSkills: (role: string) => Promise<void>;
  loadRoleMCPTools: (role: string) => Promise<void>;
  createAgent: (req: CreateAgentRequest) => Promise<AgentProfile>;
  updateAgent: (name: string, req: UpdateAgentRequest) => Promise<void>;
  deleteAgent: (name: string) => Promise<void>;
}

export const useExpertAgentStore = create<ExpertAgentState>((set) => ({
  agents: [],
  roleSkills: [],
  roleMCPTools: [],
  loading: false,

  loadAgents: async () => {
    set({ loading: true });
    const data = await expertApi.listManageableAgents();
    set({ agents: data.agents || [], loading: false });
  },

  loadRoleSkills: async (role) => {
    const data = await expertApi.getRoleSkills(role);
    set({ roleSkills: data.skills || [] });
  },

  loadRoleMCPTools: async (role) => {
    const data = await expertApi.getRoleMCPTools(role);
    set({ roleMCPTools: data.mcp_tools || [] });
  },

  createAgent: async (req) => {
    const data = await expertApi.createAgent(req);
    return data.agent;
  },

  updateAgent: async (name, req) => {
    await expertApi.updateAgent(name, req);
  },

  deleteAgent: async (name) => {
    await expertApi.deleteAgent(name);
  },
}));
