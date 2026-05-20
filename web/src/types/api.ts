export type UserRole = 'admin' | 'manager' | 'operator' | 'viewer';

export interface ChatRequest {
  content: string;
  user_id?: string;
  session_id?: string;
}

export interface ChatResponse {
  content: string;
  session_id: string;
}

export interface AuthTokenRequest {
  user_id: string;
  role: UserRole;
}

export interface AuthTokenResponse {
  token: string;
  user_id: string;
  role: string;
}

export interface ApprovalItem {
  approval_id: string;
  level: string;
  reason: string;
  details: string;
}

export interface CronTaskCreate {
  name: string;
  cron_expression: string;
  user_id: string;
  prompt: string;
  channel?: string;
}

export interface CronTaskItem {
  task_id: string;
  name: string;
  cron_expression: string;
  user_id: string;
  prompt: string;
  channel: string;
  status: string;
}

export interface BackgroundTaskCreate {
  name: string;
  prompt: string;
  user_id?: string;
}

export interface BackgroundTaskItem {
  task_id: string;
  name: string;
  user_id: string;
  prompt: string;
  status: string;
  created_at: string;
  completed_at: string;
  result: string;
  error: string | null;
}

export interface SkillVerifyRequest {
  requirement: string;
  user_id?: string;
}

export interface SkillVerifyResult {
  passed: boolean;
  skill_content: string;
  evaluation: string;
  rounds: number;
  suggestions: string[];
}

export interface GEPAOptimizeResult {
  optimized: boolean;
  original_score: number;
  best_candidate_score: number | null;
  candidates_count: number;
}

export interface EvolutionAutoResult {
  needs_evolution: boolean;
  reason: string;
  suggested_skill_name: string;
}

export interface PluginInfo {
  name: string;
  description: string;
  skills: string[];
  location?: string;
}

export interface MemoryFileResponse {
  user_id: string;
  file: string;
  content: string;
}

export interface SessionListResponse {
  user_id: string;
  sessions: { session_id: string; agent_id: string }[];
}

export interface SessionMessagesResponse {
  user_id: string;
  session_id: string;
  messages: SessionMessage[];
}

export interface SessionMessage {
  timestamp: string;
  type: string;
  content: string;
  tool_calls?: { id: string; name: string; args: Record<string, unknown> }[];
  tool_call_id?: string;
  name?: string;
}