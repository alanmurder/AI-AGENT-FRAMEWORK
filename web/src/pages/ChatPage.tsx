import { useEffect, useState } from 'react';
import { Input, Button } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { useChatStore } from '../store/chatStore';
import { useAuthStore } from '../store/authStore';
import { useAgentChat } from '../hooks/useAgentChat';
import ChatBubble from '../components/ChatBubble';
import StreamOutput from '../components/StreamOutput';
import ToolCallCard from '../components/ToolCallCard';
import SessionList from '../components/SessionList';

export default function ChatPage() {
  const chatStore = useChatStore();
  const authStore = useAuthStore();
  const { startChat, send, switchAgent, connecting } = useAgentChat();
  const [inputValue, setInputValue] = useState('');
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const agentFromUrl = searchParams.get('agent');
    if (agentFromUrl && agentFromUrl !== authStore.agentId) {
      switchAgent(agentFromUrl);
    }
  }, [searchParams]);

  useEffect(() => {
    if (authStore.isAuthenticated) {
      chatStore.loadSessions(authStore.userId);
      startChat();
    }
  }, [authStore.isAuthenticated]);

  const handleSend = () => {
    if (!inputValue.trim()) return;
    send(inputValue.trim());
    setInputValue('');
  };

  const agentLabel = authStore.agentId ? authStore.agentId : '默认智能体';

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 64px)' }}>
      <SessionList onSwitchAgent={switchAgent} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #e8e8e8', fontSize: 14, color: '#666' }}>
          与 <span style={{ color: '#1890ff', fontWeight: 500 }}>{agentLabel}</span> 对话
          {chatStore.currentSessionId && <span> · 会话 #{chatStore.currentSessionId.slice(0, 8)}</span>}
        </div>
        <div style={{ flex: 1, padding: 16, overflowY: 'auto', background: '#fafafa' }}>
          {chatStore.messages.map((msg) => (
            msg.type === 'tool' ? null : <ChatBubble key={msg.id} message={msg} />
          ))}
          {chatStore.activeToolCalls.map((tc) => (
            <ToolCallCard key={tc.id} toolCall={tc} />
          ))}
          <StreamOutput />
        </div>
        <div style={{ padding: '12px 16px', borderTop: '1px solid #e8e8e8', display: 'flex', gap: 8 }}>
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onPressEnter={handleSend}
            placeholder={connecting ? '正在连接...' : '输入消息...'}
            size="large"
            disabled={connecting}
          />
          <Button type="primary" size="large" onClick={handleSend} disabled={connecting} loading={connecting}>
            {connecting ? '连接中' : '发送'}
          </Button>
        </div>
      </div>
    </div>
  );
}