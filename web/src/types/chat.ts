export interface Message {
  id: string;
  type: 'human' | 'ai' | 'tool';
  content: string;
  timestamp: string;
  tool_calls?: ToolCallInfo[];
}

export interface ToolCallInfo {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export interface SessionInfo {
  id: string;
  title: string;
  lastMessageTime: string;
  agentId?: string;
}

export type StreamEventType = 'session_start' | 'chunk' | 'tool_call' | 'done' | 'error';

export interface StreamEvent {
  type: StreamEventType;
  content?: string;
  name?: string;
  args?: Record<string, unknown>;
  user_id?: string;
  session_id?: string;
}