import { useRef, useCallback, useEffect, useState } from 'react';
import type { StreamEvent } from '../types/chat';
import { useChatStore } from '../store/chatStore';
import { useAuthStore } from '../store/authStore';

interface WebSocketOptions {
  onEvent?: (event: StreamEvent) => void;
  autoConnect?: boolean;
}

export function isGatewayAuthError(event: StreamEvent) {
  if (event.type !== 'error') return false;
  const content = (event.content || '').toLowerCase();
  return content.includes('invalid or missing authentication');
}

export function useWebSocket(options: WebSocketOptions = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const authFailed = useRef(false);
  const pendingQueue = useRef<string[]>([]);
  const pendingAgentRef = useRef<string>('');
  const maxReconnects = 3;
  const chatStore = useChatStore();
  const authStore = useAuthStore();
  const [connecting, setConnecting] = useState(false);

  const disconnect = useCallback(() => {
    // Cancel any pending reconnect
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    reconnectAttempts.current = maxReconnects;

    const oldWs = wsRef.current;
    wsRef.current = null;
    // Close AFTER nulling wsRef so onclose sees it's stale
    oldWs?.close();
  }, []);

  const connect = useCallback((agentId?: string) => {
    if (authFailed.current) return;
    if (!authStore.token) return;

    // Abort any in-progress connection
    if (wsRef.current && wsRef.current.readyState !== WebSocket.OPEN) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    // Cancel pending reconnect if any
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }

    reconnectAttempts.current = 0;
    authFailed.current = false;
    if (agentId !== undefined) {
      pendingAgentRef.current = agentId;
    }
    setConnecting(true);

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      // Discard if this connection has been replaced
      if (ws !== wsRef.current) {
        ws.close();
        return;
      }
      setConnecting(false);

      const agent_id = pendingAgentRef.current;
      ws.send(JSON.stringify({
        token: authStore.token,
        user_id: authStore.userId,
        agent_id,
      }));

      // Flush queued messages
      while (pendingQueue.current.length > 0) {
        const msg = pendingQueue.current.shift()!;
        ws.send(JSON.stringify({ content: msg }));
      }
    };

    ws.onmessage = (event) => {
      try {
        const data: StreamEvent = JSON.parse(event.data);
        if (isGatewayAuthError(data)) {
          authFailed.current = true;
          authStore.logout();
          disconnect();
          return;
        }
        chatStore.handleStreamEvent(data);
        options.onEvent?.(data);
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      setConnecting(false);
      if (ws !== wsRef.current) return;
      if (authFailed.current) return;
      if (reconnectAttempts.current < maxReconnects) {
        reconnectAttempts.current += 1;
        reconnectTimer.current = setTimeout(() => connect(pendingAgentRef.current), 5000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [authStore.token, authStore.userId, chatStore]);

  const sendMessage = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ content }));
    } else {
      // Queue the message — will be sent when connection opens
      pendingQueue.current.push(content);
    }
  }, []);

  useEffect(() => {
    if (options.autoConnect && authStore.isAuthenticated && authStore.token) {
      authFailed.current = false;
      connect(authStore.agentId);
    }
    return () => {
      disconnect();
    };
  }, [authStore.isAuthenticated]);

  return { connect, disconnect, sendMessage, connecting, wsRef };
}
