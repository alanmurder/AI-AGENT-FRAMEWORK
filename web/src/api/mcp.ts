import client from './client';
import type { MCPServerConfig, MCPToolInfo, MCPServerDetail, MCPImportResult } from '../types/api';

export async function listMCPServers(): Promise<{ servers: MCPServerConfig[] }> {
  const res = await client.get('/api/mcp/servers');
  return res.data;
}

export async function getMCPServer(name: string): Promise<MCPServerDetail> {
  const res = await client.get(`/api/mcp/servers/${name}`);
  return res.data;
}

export async function createMCPServer(req: MCPServerConfig): Promise<{ message: string; name: string }> {
  const res = await client.post('/api/mcp/servers', req);
  return res.data;
}

export async function importMCPServers(file: File, overwrite = true): Promise<MCPImportResult> {
  const form = new FormData();
  form.append('file', file);
  const res = await client.post('/api/mcp/servers/import', form, { params: { overwrite } });
  return res.data;
}

export async function updateMCPServer(name: string, req: MCPServerConfig): Promise<{ message: string; name: string }> {
  const res = await client.put(`/api/mcp/servers/${name}`, req);
  return res.data;
}

export async function deleteMCPServer(name: string): Promise<{ deleted: string }> {
  const res = await client.delete(`/api/mcp/servers/${name}`);
  return res.data;
}

export async function connectMCPServer(name: string): Promise<{ status: string; server: string; connected: boolean; tools: number }> {
  const res = await client.post(`/api/mcp/servers/${name}/connect`);
  return res.data;
}

export async function disconnectMCPServer(name: string): Promise<{ status: string; server: string; connected: boolean }> {
  const res = await client.post(`/api/mcp/servers/${name}/disconnect`);
  return res.data;
}

export async function listMCPTools(role?: string): Promise<{ tools: MCPToolInfo[] }> {
  const params = role ? { role } : {};
  const res = await client.get('/api/mcp/tools', { params });
  return res.data;
}
