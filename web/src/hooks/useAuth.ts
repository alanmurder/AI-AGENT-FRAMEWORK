import { useCallback } from 'react';
import { useAuthStore } from '../store/authStore';
import type { UserRole } from '../types/api';

export function useAuth() {
  const store = useAuthStore();

  const login = useCallback(async (userId: string, password: string) => {
    await store.login(userId, password);
  }, [store]);

  const logout = useCallback(() => {
    store.logout();
  }, [store]);

  const hasRole = useCallback((roles: UserRole[]) => {
    return roles.includes(store.role);
  }, [store.role]);

  const isAdmin = store.role === 'admin';
  const isManager = store.role === 'manager';
  const isOperator = store.role === 'operator';
  const isViewer = store.role === 'viewer';

  return {
    ...store,
    login,
    logout,
    hasRole,
    isAdmin,
    isManager,
    isOperator,
    isViewer,
  };
}