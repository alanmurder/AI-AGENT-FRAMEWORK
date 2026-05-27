import { beforeEach, describe, expect, test, vi } from 'vitest';
import { useChatStore } from './chatStore';
import type { Message } from '../types/chat';
import { loadSessionMessages } from '../api/memory';

vi.mock('../api/memory', () => ({
  listSessions: vi.fn(),
  loadSessionMessages: vi.fn(),
}));

function resetStore() {
  useChatStore.setState({
    sessions: [],
    currentSessionId: '',
    messages: [],
    streamingContent: '',
    isStreaming: false,
    activeToolCalls: [],
    sessionSkills: [],
    sessionRole: '',
    activeProcessEvents: [],
  });
}

describe('chat process events', () => {
  beforeEach(() => {
    resetStore();
  });

  test('stores session skill manifest from stream events', () => {
    useChatStore.getState().handleStreamEvent({
      type: 'skill_manifest',
      role: 'operator',
      session_id: 'sess-1',
      skills: [
        { name: 'file_manager', description: 'Files', category: 'file_manager' },
        { name: 'knowledge_search', description: 'Search', category: 'knowledge_search' },
      ],
    });

    expect(useChatStore.getState().sessionRole).toBe('operator');
    expect(useChatStore.getState().sessionSkills.map((skill) => skill.name)).toEqual([
      'file_manager',
      'knowledge_search',
    ]);
  });

  test('seeds each user turn with loaded skill manifest and finalizes process events', () => {
    useChatStore.setState({
      sessionSkills: [{ name: 'file_manager', description: 'Files', category: 'file_manager' }],
      sessionRole: 'operator',
    });

    const userMessage: Message = {
      id: 'user-1',
      type: 'human',
      content: 'hello',
      timestamp: '2026-05-27T00:00:00.000Z',
    };

    useChatStore.getState().beginUserTurn(userMessage);
    useChatStore.getState().handleStreamEvent({
      type: 'skill_use',
      name: 'file_manager',
      phase: 'answering',
      reason: 'Need a file',
      session_id: 'sess-1',
    });
    useChatStore.getState().handleStreamEvent({ type: 'chunk', content: 'Answer' });
    useChatStore.getState().handleStreamEvent({ type: 'done' });

    const state = useChatStore.getState();
    expect(state.messages).toHaveLength(2);
    expect(state.messages[1].type).toBe('ai');
    expect(state.messages[1].process_events?.map((event) => event.type)).toEqual([
      'skill_manifest',
      'skill_use',
    ]);
    expect(state.activeProcessEvents).toEqual([]);
  });

  test('adds progress and tool calls to active process events', () => {
    useChatStore.getState().handleStreamEvent({
      type: 'progress',
      stage: 'preparing_response',
      content: 'Preparing response',
      session_id: 'sess-1',
    });
    useChatStore.getState().handleStreamEvent({
      type: 'tool_call',
      id: 'tc1',
      name: 'file_read',
      args: { path: 'a.txt' },
      session_id: 'sess-1',
    });

    const events = useChatStore.getState().activeProcessEvents;
    expect(events.map((event) => event.type)).toEqual(['progress', 'tool_call']);
    expect(useChatStore.getState().activeToolCalls[0].name).toBe('file_read');
  });

  test('finalizes process-only turns with an empty AI message', () => {
    useChatStore.getState().handleStreamEvent({
      type: 'progress',
      stage: 'preparing_response',
      content: 'Preparing response',
      session_id: 'sess-1',
    });
    useChatStore.getState().handleStreamEvent({ type: 'done' });

    const state = useChatStore.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].type).toBe('ai');
    expect(state.messages[0].content).toBe('');
    expect(state.messages[0].process_events?.map((event) => event.type)).toEqual(['progress']);
    expect(state.activeProcessEvents).toEqual([]);
  });

  test('normalizes missing process event ids when loading session history', async () => {
    vi.mocked(loadSessionMessages).mockResolvedValue({
      user_id: 'user-1',
      session_id: 'sess-1',
      messages: [
        {
          timestamp: '2026-05-27T00:00:00.000Z',
          type: 'ai',
          content: 'Loaded',
          process_events: [
            { type: 'progress', stage: 'preparing_response', content: 'Preparing response' },
            { id: 'existing-id', type: 'skill_use', name: 'file_manager' },
          ],
        } as never,
      ],
    });

    await useChatStore.getState().loadSessionMessages('user-1', 'sess-1');

    const processEvents = useChatStore.getState().messages[0].process_events;
    expect(processEvents?.map((event) => event.id)).toEqual([
      'sess-1-0-process-0',
      'existing-id',
    ]);
  });

  test('clears stale live state when loading session history', async () => {
    useChatStore.setState({
      streamingContent: 'stale',
      isStreaming: true,
      activeToolCalls: [{ id: 'tc1', name: 'file_read', args: { path: 'a.txt' } }],
      activeProcessEvents: [{
        id: 'progress-1',
        type: 'progress',
        stage: 'preparing_response',
        content: 'Preparing response',
      }],
      sessionSkills: [{ name: 'file_manager', description: 'Files', category: 'file_manager' }],
      sessionRole: 'operator',
    });
    vi.mocked(loadSessionMessages).mockResolvedValue({
      user_id: 'user-1',
      session_id: 'sess-1',
      messages: [],
    });

    await useChatStore.getState().loadSessionMessages('user-1', 'sess-1');

    const state = useChatStore.getState();
    expect(state.streamingContent).toBe('');
    expect(state.isStreaming).toBe(false);
    expect(state.activeToolCalls).toEqual([]);
    expect(state.activeProcessEvents).toEqual([]);
    expect(state.sessionSkills).toEqual([]);
    expect(state.sessionRole).toBe('');
  });
});
