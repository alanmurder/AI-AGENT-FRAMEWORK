import client from './client';
import type { MemoryFileResponse, SessionListResponse, SessionMessagesResponse } from '../types/api';

export async function getMemoryFile(userId: string, file: string = 'MEMORY.md'): Promise<MemoryFileResponse> {
  const res = await client.get(`/api/memory/${userId}`, { params: { file } });
  return res.data;
}

export async function listSessions(userId: string): Promise<SessionListResponse> {
  const res = await client.get(`/api/sessions/${userId}`);
  return res.data;
}

export async function loadSessionMessages(userId: string, sessionId: string): Promise<SessionMessagesResponse> {
  const res = await client.get(`/api/sessions/${userId}/${sessionId}`);
  return res.data;
}