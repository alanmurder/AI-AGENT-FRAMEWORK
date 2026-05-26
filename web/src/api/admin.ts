import client from './client';
import type {
  ApprovalItem,
  CronTaskCreate,
  CronTaskItem,
  BackgroundTaskCreate,
  BackgroundTaskItem,
  SkillVerifyRequest,
  SkillVerifyResult,
  GEPAOptimizeResult,
  EvolutionAutoResult,
  PluginInfo,
  SkillImportResult,
  SkillInfo,
} from '../types/api';

export async function listPendingApprovals(): Promise<{ pending_approvals: ApprovalItem[] }> {
  const res = await client.get('/api/approvals/pending');
  return res.data;
}

export async function approveApproval(approvalId: string): Promise<{ approval_id: string; status: string }> {
  const res = await client.post(`/api/approvals/${approvalId}/approve`);
  return res.data;
}

export async function rejectApproval(approvalId: string): Promise<{ approval_id: string; status: string }> {
  const res = await client.post(`/api/approvals/${approvalId}/reject`);
  return res.data;
}

export async function listCronTasks(userId: string): Promise<CronTaskItem[]> {
  const res = await client.get(`/api/crons/${userId}`);
  return res.data;
}

export async function createCronTask(req: CronTaskCreate): Promise<CronTaskItem> {
  const res = await client.post('/api/crons', req);
  return res.data;
}

export async function deleteCronTask(taskId: string): Promise<{ deleted: string }> {
  const res = await client.delete(`/api/crons/${taskId}`);
  return res.data;
}

export async function listBackgroundTasks(userId: string): Promise<BackgroundTaskItem[]> {
  const res = await client.get(`/api/background/${userId}`);
  return res.data;
}

export async function getBackgroundTask(taskId: string): Promise<BackgroundTaskItem> {
  const res = await client.get(`/api/background/task/${taskId}`);
  return res.data;
}

export async function submitBackgroundTask(req: BackgroundTaskCreate): Promise<BackgroundTaskItem> {
  const res = await client.post('/api/background', req);
  return res.data;
}

export async function listSkills(): Promise<{ manifest: Record<string, unknown> | string; skills?: SkillInfo[] }> {
  const res = await client.get('/api/skills');
  return res.data;
}

export async function importSkillZip(file: File, overwrite = true): Promise<SkillImportResult> {
  const form = new FormData();
  form.append('file', file);
  const res = await client.post('/api/skills/import-zip', form, { params: { overwrite } });
  return res.data;
}

export async function verifySkill(req: SkillVerifyRequest): Promise<SkillVerifyResult> {
  const res = await client.post('/api/skills/verify', req);
  return res.data;
}

export async function optimizeSkill(skillName: string): Promise<GEPAOptimizeResult> {
  const res = await client.post(`/api/skills/optimize/${skillName}`);
  return res.data;
}

export async function triggerAutoEvolution(userId?: string): Promise<EvolutionAutoResult> {
  const res = await client.post('/api/evolution/auto', { user_id: userId });
  return res.data;
}

export async function listPlugins(): Promise<{ plugins: PluginInfo[] }> {
  const res = await client.get('/api/plugins');
  return res.data;
}

export async function getPlugin(name: string): Promise<PluginInfo> {
  const res = await client.get(`/api/plugins/${name}`);
  return res.data;
}
