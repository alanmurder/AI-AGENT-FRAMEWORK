import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SkillManager from './SkillManager';
import { useAdminStore } from '../store/adminStore';

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

const loadSkills = vi.fn().mockResolvedValue(undefined);
const loadRbacResources = vi.fn().mockResolvedValue(undefined);
const updateSkillRoles = vi.fn().mockResolvedValue(undefined);
const initialAdminState = useAdminStore.getState();

describe('SkillManager role permissions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAdminStore.setState({
      skills: [{ name: 'file_manager', description: 'Files', category: 'file_manager', access: 'report' }],
      rbacResources: {
        roles: ['admin', 'manager', 'operator', 'viewer'],
        skills: [{ name: 'file_manager', description: 'Files', access: 'report', roles: ['admin'] }],
        mcp_servers: [],
      },
      loadSkills,
      loadRbacResources,
      updateSkillRoles,
    });
  });

  afterEach(() => {
    cleanup();
    useAdminStore.setState(initialAdminState, true);
  });

  test('saves updated skill role permissions', async () => {
    render(<SkillManager />);

    expect(await screen.findByText('file_manager')).toBeTruthy();

    fireEvent.click(screen.getByRole('checkbox', { name: 'operator' }));
    fireEvent.click(screen.getByRole('button', { name: '保存角色权限' }));

    await waitFor(() => {
      expect(updateSkillRoles).toHaveBeenCalledWith('file_manager', ['admin', 'operator']);
    });
  });

  test('does not save permissions before RBAC resources load', async () => {
    useAdminStore.setState({ rbacResources: null });

    render(<SkillManager />);

    expect(await screen.findByText('file_manager')).toBeTruthy();
    expect((screen.getByRole('button', { name: '保存角色权限' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
