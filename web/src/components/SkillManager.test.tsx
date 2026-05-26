import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SkillManager from './SkillManager';
import { useAdminStore } from '../store/adminStore';
import { useAuthStore } from '../store/authStore';
import * as adminApi from '../api/admin';

vi.mock('../api/admin', () => ({
  verifySkill: vi.fn(),
  optimizeSkill: vi.fn(),
  triggerAutoEvolution: vi.fn(),
  importSkillZip: vi.fn(),
}));

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
const initialAuthState = useAuthStore.getState();

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
    useAuthStore.setState({
      userId: 'admin',
      role: 'admin',
      token: 'token',
      agentId: '',
      isAuthenticated: true,
    });
  });

  afterEach(() => {
    cleanup();
    useAdminStore.setState(initialAdminState, true);
    useAuthStore.setState(initialAuthState, true);
  });

  test('saves updated skill role permissions', async () => {
    render(<SkillManager />);

    expect(await screen.findByText('file_manager')).toBeTruthy();

    fireEvent.click(screen.getByRole('checkbox', { name: 'operator' }));
    fireEvent.click(screen.getByRole('button', { name: 'save skill roles' }));

    await waitFor(() => {
      expect(updateSkillRoles).toHaveBeenCalledWith('file_manager', ['admin', 'operator']);
    });
  });

  test('does not save permissions before RBAC resources load', async () => {
    useAdminStore.setState({ rbacResources: null });

    render(<SkillManager />);

    expect(await screen.findByText('file_manager')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'save skill roles' }) as HTMLButtonElement).disabled).toBe(true);
  });

  test('does not save permissions when skill is missing from RBAC resources', async () => {
    useAdminStore.setState({
      skills: [
        { name: 'file_manager', description: 'Files', category: 'file_manager', access: 'report' },
        { name: 'new_skill', description: 'New', category: 'file_manager', access: 'report' },
      ],
    });

    render(<SkillManager />);

    expect(screen.queryByText('new_skill')).toBeNull();
    expect(screen.getAllByRole('button', { name: 'save skill roles' })).toHaveLength(1);
  });

  test('renders permission rows from RBAC resources even when skills are role filtered', async () => {
    useAdminStore.setState({
      skills: [{ name: 'file_manager', description: 'Files', category: 'file_manager', access: 'report' }],
      rbacResources: {
        roles: ['admin', 'manager', 'operator', 'viewer'],
        skills: [
          { name: 'file_manager', description: 'Files', access: 'report', roles: ['admin'] },
          { name: 'hidden_skill', description: 'Hidden', access: 'enterprise', roles: ['operator'] },
        ],
        mcp_servers: [],
      },
    });

    render(<SkillManager />);

    expect(await screen.findByText('hidden_skill')).toBeTruthy();
    const buttons = screen.getAllByRole('button', { name: 'save skill roles' }) as HTMLButtonElement[];
    expect(buttons[1].disabled).toBe(false);
  });

  test('refreshes RBAC resources after importing a skill zip', async () => {
    vi.mocked(adminApi.importSkillZip).mockResolvedValue({ imported: ['new_skill'], skipped: [] });

    const { container } = render(<SkillManager />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['zip'], 'skill.zip', { type: 'application/zip' });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(adminApi.importSkillZip).toHaveBeenCalledWith(file);
      expect(loadRbacResources).toHaveBeenCalledTimes(2);
    });
  });

  test('does not load or render role permission controls for managers', async () => {
    useAuthStore.setState({
      userId: 'manager',
      role: 'manager',
      token: 'token',
      agentId: '',
      isAuthenticated: true,
    });
    useAdminStore.setState({ rbacResources: null });

    render(<SkillManager />);

    expect(await screen.findByText('file_manager')).toBeTruthy();
    expect(loadRbacResources).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'save skill roles' })).toBeNull();
  });
});
