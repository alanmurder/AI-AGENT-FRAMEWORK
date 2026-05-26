import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

vi.mock('./pages/ChatPage', () => ({ default: () => <div>Chat Page</div> }));
vi.mock('./pages/AgentMarket', () => ({ default: () => <div>Agent Market</div> }));
vi.mock('./pages/AdminPanel', () => ({ default: () => <div>Admin Panel</div> }));

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import App from './App';
import { useAuthStore } from './store/authStore';

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

function resetAuthState() {
  localStorage.clear();
  useAuthStore.setState({
    userId: '',
    role: 'viewer',
    token: '',
    agentId: '',
    isAuthenticated: false,
  });
}

describe('App authentication routing', () => {
  beforeEach(() => {
    resetAuthState();
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    cleanup();
    resetAuthState();
  });

  test('redirects protected routes to login when unauthenticated', async () => {
    window.history.pushState({}, '', '/chat');

    render(<App />);

    expect(await screen.findByText('AI Agent Platform 登录')).toBeTruthy();
    expect(screen.queryByText('Chat Page')).toBeNull();
  });

  test('logout clears auth state and returns to login', async () => {
    localStorage.setItem('token', 'token');
    localStorage.setItem('userId', 'admin');
    localStorage.setItem('role', 'admin');
    useAuthStore.setState({
      userId: 'admin',
      role: 'admin',
      token: 'token',
      agentId: '',
      isAuthenticated: true,
    });
    window.history.pushState({}, '', '/chat');

    render(<App />);

    expect(await screen.findByText('Chat Page')).toBeTruthy();
    fireEvent.click(screen.getByText('退出'));

    expect(await screen.findByText('AI Agent Platform 登录')).toBeTruthy();
    expect(localStorage.getItem('token')).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
