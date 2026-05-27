export interface SkillSummary {
  name: string;
  description: string;
  category: string;
}

export interface ToolCallInfo {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export type ProcessEvent =
  | {
      id: string;
      type: 'skill_manifest';
      skills: SkillSummary[];
      role?: string;
      session_id?: string;
      agent_id?: string;
    }
  | {
      id: string;
      type: 'skill_use';
      name: string;
      phase?: string;
      reason?: string;
      session_id?: string;
      agent_id?: string;
    }
  | {
      id: string;
      type: 'progress';
      stage?: string;
      content?: string;
      session_id?: string;
      agent_id?: string;
    }
  | ({
      type: 'tool_call';
      session_id?: string;
      agent_id?: string;
    } & ToolCallInfo);

export interface Message {
  id: string;
  type: 'human' | 'ai' | 'tool';
  content: string;
  timestamp: string;
  tool_calls?: ToolCallInfo[];
  process_events?: ProcessEvent[];
}

export interface SessionInfo {
  id: string;
  title: string;
  lastMessageTime: string;
  agentId?: string;
}

export type StreamEventType =
  | 'session_start'
  | 'chunk'
  | 'tool_call'
  | 'skill_manifest'
  | 'skill_use'
  | 'progress'
  | 'done'
  | 'error';

export interface StreamEvent {
  type: StreamEventType;
  content?: string;
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
  skills?: SkillSummary[];
  role?: string;
  phase?: string;
  reason?: string;
  stage?: string;
  user_id?: string;
  session_id?: string;
  agent_id?: string;
}
