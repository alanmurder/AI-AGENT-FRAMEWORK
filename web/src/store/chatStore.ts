import { create } from 'zustand';
import type { Message, ProcessEvent, SkillSummary, ToolCallInfo, SessionInfo, StreamEvent } from '../types/chat';
import { listSessions, loadSessionMessages } from '../api/memory';

interface ChatState {
  sessions: SessionInfo[];
  currentSessionId: string;
  messages: Message[];
  streamingContent: string;
  isStreaming: boolean;
  activeToolCalls: ToolCallInfo[];
  sessionSkills: SkillSummary[];
  sessionRole: string;
  activeProcessEvents: ProcessEvent[];

  loadSessions: (userId: string) => Promise<void>;
  loadSessionMessages: (userId: string, sessionId: string) => Promise<void>;
  startNewSession: () => void;
  beginUserTurn: (message: Message) => void;
  addStreamingChunk: (content: string) => void;
  finalizeStream: () => void;
  addToolCall: (toolCall: ToolCallInfo) => void;
  addProcessEvent: (event: ProcessEvent) => void;
  handleStreamEvent: (event: StreamEvent) => void;
  resetStream: () => void;
}

function processEventId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSessionId: '',
  messages: [],
  streamingContent: '',
  isStreaming: false,
  activeToolCalls: [],
  sessionSkills: [],
  sessionRole: '',
  activeProcessEvents: [],

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
    const messages: Message[] = res.messages.map((m, i) => {
      const persistedMessage = m as typeof m & { process_events?: ProcessEvent[] };
      return {
        id: `${sessionId}-${i}`,
        type: m.type as Message['type'],
        content: m.content,
        timestamp: m.timestamp,
        tool_calls: m.tool_calls?.map((tc) => ({ id: tc.id, name: tc.name, args: tc.args })),
        process_events: persistedMessage.process_events?.map((event) => ({ ...event })),
      };
    });
    set({ messages, currentSessionId: sessionId });
  },

  startNewSession: () => set({
    messages: [],
    currentSessionId: '',
    streamingContent: '',
    isStreaming: false,
    activeToolCalls: [],
    sessionSkills: [],
    sessionRole: '',
    activeProcessEvents: [],
  }),

  beginUserTurn: (message: Message) => set((state) => {
    const activeProcessEvents: ProcessEvent[] = state.sessionSkills.length > 0
      ? [{
          id: processEventId('skill-manifest'),
          type: 'skill_manifest',
          skills: state.sessionSkills,
          role: state.sessionRole || undefined,
          session_id: state.currentSessionId || undefined,
        }]
      : [];

    return {
      messages: [...state.messages, message],
      streamingContent: '',
      isStreaming: true,
      activeToolCalls: [],
      activeProcessEvents,
    };
  }),

  addStreamingChunk: (content: string) => set((state) => ({
    streamingContent: state.streamingContent + content,
    isStreaming: true,
  })),

  finalizeStream: () => set((state) => {
    if (!state.streamingContent) {
      return {
        isStreaming: false,
        activeToolCalls: [],
        activeProcessEvents: [],
      };
    }

    const processEvents = state.activeProcessEvents.map((event) => ({ ...event }));
    const newMessage: Message = {
      id: `${state.currentSessionId}-stream-${Date.now()}`,
      type: 'ai',
      content: state.streamingContent,
      timestamp: new Date().toISOString(),
      tool_calls: state.activeToolCalls,
      process_events: processEvents,
    };
    return {
      messages: [...state.messages, newMessage],
      streamingContent: '',
      isStreaming: false,
      activeToolCalls: [],
      activeProcessEvents: [],
    };
  }),

  addToolCall: (toolCall: ToolCallInfo) => set((state) => ({
    activeToolCalls: [...state.activeToolCalls, toolCall],
  })),

  addProcessEvent: (event: ProcessEvent) => set((state) => ({
    activeProcessEvents: [...state.activeProcessEvents, event],
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
        {
          const toolCall: ToolCallInfo = {
            id: event.id || processEventId('tc'),
            name: event.name || '',
            args: event.args || {},
          };
          state.addToolCall(toolCall);
          state.addProcessEvent({
            ...toolCall,
            type: 'tool_call',
            session_id: event.session_id,
            agent_id: event.agent_id,
          });
        }
        break;
      case 'skill_manifest':
        {
          const skills = event.skills || [];
          set({
            sessionSkills: skills,
            sessionRole: event.role || '',
          });
          get().addProcessEvent({
            id: event.id || processEventId('skill-manifest'),
            type: 'skill_manifest',
            skills,
            role: event.role,
            session_id: event.session_id,
            agent_id: event.agent_id,
          });
        }
        break;
      case 'skill_use':
        state.addProcessEvent({
          id: event.id || processEventId('skill-use'),
          name: event.name || '',
          type: 'skill_use',
          phase: event.phase,
          reason: event.reason,
          session_id: event.session_id,
          agent_id: event.agent_id,
        });
        break;
      case 'progress':
        state.addProcessEvent({
          id: event.id || processEventId('progress'),
          type: 'progress',
          stage: event.stage,
          content: event.content,
          session_id: event.session_id,
          agent_id: event.agent_id,
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

  resetStream: () => set({ streamingContent: '', isStreaming: false, activeToolCalls: [], activeProcessEvents: [] }),
}));
