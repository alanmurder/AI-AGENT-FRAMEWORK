import { beforeEach, describe, expect, test } from 'vitest';
import { useChatStore } from './chatStore';
import type { Message } from '../types/chat';

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
});
