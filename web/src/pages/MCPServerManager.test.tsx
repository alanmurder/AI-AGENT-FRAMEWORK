import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import MCPServerManager from './MCPServerManager';
import { useAdminStore } from '../store/adminStore';
import { useMCPStore } from '../store/mcpStore';
import * as mcpApi from '../api/mcp';

vi.mock('../api/mcp', () => ({
  getMCPServer: vi.fn(),
  listMCPServers: vi.fn(),
  listMCPTools: vi.fn(),
  createMCPServer: vi.fn(),
  importMCPServers: vi.fn(),
  updateMCPServer: vi.fn(),
  deleteMCPServer: vi.fn(),
  connectMCPServer: vi.fn(),
  disconnectMCPServer: vi.fn(),
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

const loadServers = vi.fn().mockResolvedValue(undefined);
const createServer = vi.fn().mockResolvedValue(undefined);
const updateServer = vi.fn().mockResolvedValue(undefined);
const deleteServer = vi.fn().mockResolvedValue(undefined);
const connectServer = vi.fn().mockResolvedValue({ status: 'connected', server: 'filesystem', tools: 0 });
const disconnectServer = vi.fn().mockResolvedValue(undefined);
const loadTools = vi.fn().mockResolvedValue(undefined);
const loadRbacResources = vi.fn().mockResolvedValue(undefined);
const updateMCPServerRoles = vi.fn().mockResolvedValue(undefined);
const initialMCPState = useMCPStore.getState();
const initialAdminState = useAdminStore.getState();

function setMCPStore() {
  useMCPStore.setState({
    servers: [{
      name: 'filesystem',
      transport: 'stdio',
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-filesystem'],
      enabled: true,
      env: {},
    }],
    tools: [],
    loading: false,
    loadServers,
    loadTools,
    createServer,
    updateServer,
    deleteServer,
    connectServer,
    disconnectServer,
  });
}

function setLoadedRbacStore() {
  useAdminStore.setState({
    rbacResources: {
      roles: ['admin', 'manager', 'operator', 'viewer'],
      skills: [],
      mcp_servers: [{ name: 'filesystem', enabled: true, roles: ['admin'] }],
    },
    loadRbacResources,
    updateMCPServerRoles,
  });
}

describe('MCPServerManager role permissions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(mcpApi.getMCPServer).mockResolvedValue({
      config: {
        name: 'filesystem',
        transport: 'stdio',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-filesystem'],
        enabled: true,
        env: {},
      },
      tools: [],
    });
    setMCPStore();
    setLoadedRbacStore();
  });

  afterEach(() => {
    cleanup();
    useMCPStore.setState(initialMCPState, true);
    useAdminStore.setState(initialAdminState, true);
  });

  test('saves updated MCP server role permissions', async () => {
    render(<MCPServerManager />);

    fireEvent.click(await screen.findByText('filesystem'));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'operator' }));
    fireEvent.click(screen.getByRole('button', { name: 'save mcp server roles' }));

    await waitFor(() => {
      expect(updateMCPServerRoles).toHaveBeenCalledWith('filesystem', ['admin', 'operator']);
    });
  });

  test('does not save permissions before RBAC resources load', async () => {
    useAdminStore.setState({ rbacResources: null });

    render(<MCPServerManager />);

    fireEvent.click(await screen.findByText('filesystem'));

    expect((await screen.findByRole('button', { name: 'save mcp server roles' }) as HTMLButtonElement).disabled)
      .toBe(true);
  });

  test('saves loaded roles when RBAC resources become available', async () => {
    const asyncLoadRbacResources = vi.fn().mockImplementation(async () => {
      useAdminStore.setState({
        rbacResources: {
          roles: ['admin', 'manager', 'operator', 'viewer'],
          skills: [],
          mcp_servers: [{ name: 'filesystem', enabled: true, roles: ['admin'] }],
        },
      });
    });
    useAdminStore.setState({
      rbacResources: null,
      loadRbacResources: asyncLoadRbacResources,
      updateMCPServerRoles,
    });

    render(<MCPServerManager />);

    fireEvent.click(await screen.findByText('filesystem'));
    const saveRoles = await screen.findByRole('button', { name: 'save mcp server roles' });
    await waitFor(() => {
      expect((saveRoles as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(saveRoles);

    await waitFor(() => {
      expect(updateMCPServerRoles).toHaveBeenCalledWith('filesystem', ['admin']);
    });
  });

  test('refreshes RBAC resources after saving server config', async () => {
    render(<MCPServerManager />);

    fireEvent.click(await screen.findByText('filesystem'));
    fireEvent.click(await screen.findByRole('button', { name: 'save mcp server config' }));

    await waitFor(() => {
      expect(updateServer).toHaveBeenCalledWith('filesystem', expect.objectContaining({ name: 'filesystem' }));
      expect(loadRbacResources).toHaveBeenCalledTimes(2);
    });
  });
});
