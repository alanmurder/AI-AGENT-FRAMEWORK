import { create } from 'zustand';
import type { MCPServerConfig, MCPToolInfo } from '../types/api';
import * as mcpApi from '../api/mcp';

interface MCPState {
  servers: MCPServerConfig[];
  tools: MCPToolInfo[];
  loading: boolean;

  loadServers: () => Promise<void>;
  loadTools: (role?: string) => Promise<void>;
  createServer: (config: MCPServerConfig) => Promise<void>;
  updateServer: (name: string, config: MCPServerConfig) => Promise<void>;
  deleteServer: (name: string) => Promise<void>;
  connectServer: (name: string) => Promise<{ status: string; server: string; connected: boolean; tools: number }>;
  disconnectServer: (name: string) => Promise<void>;
}

export const useMCPStore = create<MCPState>((set) => ({
  servers: [],
  tools: [],
  loading: false,

  loadServers: async () => {
    set({ loading: true });
    const data = await mcpApi.listMCPServers();
    set({ servers: data.servers || [], loading: false });
  },

  loadTools: async (role?) => {
    const data = await mcpApi.listMCPTools(role);
    set({ tools: data.tools || [] });
  },

  createServer: async (config) => {
    await mcpApi.createMCPServer(config);
  },

  updateServer: async (name, config) => {
    await mcpApi.updateMCPServer(name, config);
  },

  deleteServer: async (name) => {
    await mcpApi.deleteMCPServer(name);
  },

  connectServer: async (name) => {
    return await mcpApi.connectMCPServer(name);
  },

  disconnectServer: async (name) => {
    await mcpApi.disconnectMCPServer(name);
  },
}));
