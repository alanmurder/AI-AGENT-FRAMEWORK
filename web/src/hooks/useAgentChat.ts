import { useCallback } from 'react';
import { useChatStore } from '../store/chatStore';
import { useAuthStore } from '../store/authStore';
import { useWebSocket } from './useWebSocket';
import type { Message } from '../types/chat';

export function useAgentChat() {
  const chatStore = useChatStore();
  const authStore = useAuthStore();
  const { connect, disconnect, sendMessage, connecting } = useWebSocket({ autoConnect: true });

  const startChat = useCallback(() => {
    chatStore.resetStream();
    connect(authStore.agentId);
  }, [chatStore, connect, authStore.agentId]);

  const send = useCallback((content: string) => {
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      type: 'human',
      content,
      timestamp: new Date().toISOString(),
    };
    chatStore.beginUserTurn(userMessage);
    sendMessage(content);
  }, [chatStore, sendMessage]);

  const switchAgent = useCallback((agentId: string) => {
    authStore.setAgentId(agentId);
    disconnect();
    chatStore.startNewSession();
    connect(agentId);
  }, [authStore, disconnect, chatStore, connect]);

  return { startChat, send, switchAgent, disconnect, connecting };
}
