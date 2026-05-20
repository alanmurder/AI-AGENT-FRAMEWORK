import client from './client';
import type { AuthTokenResponse } from '../types/api';

export async function login(user_id: string, password: string): Promise<AuthTokenResponse> {
  const res = await client.post<AuthTokenResponse>('/api/auth/token', { user_id, password });
  return res.data;
}