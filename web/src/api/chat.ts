import client from './client';
import type { ChatRequest, ChatResponse } from '../types/api';

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const res = await client.post<ChatResponse>('/api/chat', req);
  return res.data;
}

export async function sendAgentChat(agentName: string, req: ChatRequest): Promise<ChatResponse> {
  const res = await client.post<ChatResponse>(`/api/agents/${agentName}/chat`, req);
  return res.data;
}