import { create } from 'zustand';
import type { ApprovalItem, CronTaskItem, BackgroundTaskItem, PluginInfo } from '../types/api';
import * as adminApi from '../api/admin';

interface SkillInfo {
  name: string;
  description: string;
  category: string;
  access: string;
}

interface AdminState {
  pendingApprovals: ApprovalItem[];
  cronTasks: CronTaskItem[];
  backgroundTasks: BackgroundTaskItem[];
  skills: SkillInfo[];
  plugins: PluginInfo[];

  loadPendingApprovals: () => Promise<void>;
  approve: (id: string) => Promise<void>;
  reject: (id: string) => Promise<void>;
  loadCronTasks: (userId: string) => Promise<void>;
  createCronTask: (req: { name: string; cron_expression: string; prompt: string; user_id: string }) => Promise<void>;
  deleteCronTask: (taskId: string) => Promise<void>;
  loadBackgroundTasks: (userId: string) => Promise<void>;
  loadSkills: () => Promise<void>;
  loadPlugins: () => Promise<void>;
}

export const useAdminStore = create<AdminState>((set) => ({
  pendingApprovals: [],
  cronTasks: [],
  backgroundTasks: [],
  skills: [],
  plugins: [],

  loadPendingApprovals: async () => {
    const res = await adminApi.listPendingApprovals();
    set({ pendingApprovals: res.pending_approvals });
  },

  approve: async (id: string) => {
    await adminApi.approveApproval(id);
    const res = await adminApi.listPendingApprovals();
    set({ pendingApprovals: res.pending_approvals });
  },

  reject: async (id: string) => {
    await adminApi.rejectApproval(id);
    const res = await adminApi.listPendingApprovals();
    set({ pendingApprovals: res.pending_approvals });
  },

  loadCronTasks: async (userId: string) => {
    const tasks = await adminApi.listCronTasks(userId);
    set({ cronTasks: tasks });
  },

  createCronTask: async (req) => {
    await adminApi.createCronTask(req);
  },

  deleteCronTask: async (taskId: string) => {
    await adminApi.deleteCronTask(taskId);
  },

  loadBackgroundTasks: async (userId: string) => {
    const tasks = await adminApi.listBackgroundTasks(userId);
    set({ backgroundTasks: tasks });
  },

  loadSkills: async () => {
    const res = await adminApi.listSkills();
    const skills: SkillInfo[] = Object.entries(res.manifest || {}).map(([name, info]: [string, any]) => ({
      name,
      description: info?.description || '',
      category: info?.category || '',
      access: info?.access || '',
    }));
    set({ skills });
  },

  loadPlugins: async () => {
    const res = await adminApi.listPlugins();
    set({ plugins: res.plugins });
  },
}));