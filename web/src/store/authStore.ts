import { create } from 'zustand';
import type { UserRole } from '../types/api';
import { login as apiLogin } from '../api/auth';

const ANONYMOUS_ROLE: UserRole = 'viewer';
const storedToken = localStorage.getItem('token') || '';
const storedRole = storedToken
  ? ((localStorage.getItem('role') as UserRole) || ANONYMOUS_ROLE)
  : ANONYMOUS_ROLE;
const storedUserId = storedToken ? localStorage.getItem('userId') || '' : '';
const storedAgentId = storedToken ? localStorage.getItem('agentId') || '' : '';

interface AuthState {
  userId: string;
  role: UserRole;
  token: string;
  agentId: string;
  isAuthenticated: boolean;
  login: (userId: string, password: string) => Promise<void>;
  logout: () => void;
  setAgentId: (agentId: string) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  userId: storedUserId,
  role: storedRole,
  token: storedToken,
  agentId: storedAgentId,
  isAuthenticated: !!storedToken,

  login: async (userId: string, password: string) => {
    const res = await apiLogin(userId, password);
    localStorage.setItem('token', res.token);
    localStorage.setItem('userId', res.user_id);
    localStorage.setItem('role', res.role);
    localStorage.removeItem('agentId');
    set({
      userId: res.user_id,
      role: res.role as UserRole,
      token: res.token,
      isAuthenticated: true,
      agentId: '',
    });
  },

  logout: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('userId');
    localStorage.removeItem('role');
    localStorage.removeItem('agentId');
    set({ userId: '', role: ANONYMOUS_ROLE, token: '', isAuthenticated: false, agentId: '' });
  },

  setAgentId: (agentId: string) => {
    localStorage.setItem('agentId', agentId);
    set({ agentId });
  },
}));
