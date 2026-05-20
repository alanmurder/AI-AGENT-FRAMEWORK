import { create } from 'zustand';
import type { Message, ToolCallInfo, SessionInfo, StreamEvent } from '../types/chat';
import { listSessions, loadSessionMessages } from '../api/memory';

interface ChatState {
  sessions: SessionInfo[];
  currentSessionId: string;
  messages: Message[];
  streamingContent: string;
  isStreaming: boolean;
  activeToolCalls: ToolCallInfo[];

  loadSessions: (userId: string) => Promise<void>;
  loadSessionMessages: (userId: string, sessionId: string) => Promise<void>;
  startNewSession: () => void;
  addStreamingChunk: (content: string) => void;
  finalizeStream: () => void;
  addToolCall: (toolCall: ToolCallInfo) => void;
  handleStreamEvent: (event: StreamEvent) => void;
  resetStream: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSessionId: '',
  messages: [],
  streamingContent: '',
  isStreaming: false,
  activeToolCalls: [],

  loadSessions: async (userId: string) => {
    const res = await listSessions(userId);
    const sessions: SessionInfo[] = res.sessions.map((s) => ({
      id: s.session_id,
      title: s.agent_id ? `${s.agent_id} - ${s.session_id.slice(0, 8)}` : s.session_id.slice(0, 8),
      lastMessageTime: '',
      agentId: s.agent_id || undefined,
    }));
    set({ sessions });
  },

  loadSessionMessages: async (userId: string, sessionId: string) => {
    const res = await loadSessionMessages(userId, sessionId);
    const messages: Message[] = res.messages.map((m, i) => ({
      id: `${sessionId}-${i}`,
      type: m.type as Message['type'],
      content: m.content,
      timestamp: m.timestamp,
      tool_calls: m.tool_calls?.map((tc) => ({ id: tc.id, name: tc.name, args: tc.args })),
    }));
    set({ messages, currentSessionId: sessionId });
  },

  startNewSession: () => set({ messages: [], currentSessionId: '', streamingContent: '', isStreaming: false, activeToolCalls: [] }),

  addStreamingChunk: (content: string) => set((state) => ({
    streamingContent: state.streamingContent + content,
    isStreaming: true,
  })),

  finalizeStream: () => set((state) => {
    if (!state.streamingContent) return { isStreaming: false };
    const newMessage: Message = {
      id: `${state.currentSessionId}-stream-${Date.now()}`,
      type: 'ai',
      content: state.streamingContent,
      timestamp: new Date().toISOString(),
      tool_calls: state.activeToolCalls,
    };
    return {
      messages: [...state.messages, newMessage],
      streamingContent: '',
      isStreaming: false,
      activeToolCalls: [],
    };
  }),

  addToolCall: (toolCall: ToolCallInfo) => set((state) => ({
    activeToolCalls: [...state.activeToolCalls, toolCall],
  })),

  handleStreamEvent: (event: StreamEvent) => {
    const state = get();
    switch (event.type) {
      case 'session_start':
        if (event.session_id) set({ currentSessionId: event.session_id });
        break;
      case 'chunk':
        if (event.content) state.addStreamingChunk(event.content);
        break;
      case 'tool_call':
        state.addToolCall({
          id: `tc-${Date.now()}`,
          name: event.name || '',
          args: event.args || {},
        });
        break;
      case 'done':
        state.finalizeStream();
        break;
      case 'error':
        state.finalizeStream();
        break;
    }
  },

  resetStream: () => set({ streamingContent: '', isStreaming: false, activeToolCalls: [] }),
}));