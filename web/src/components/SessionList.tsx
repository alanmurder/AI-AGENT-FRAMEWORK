import { useChatStore } from '../store/chatStore';
import { useAuthStore } from '../store/authStore';
import { listAgents } from '../api/agents';
import { useEffect, useState } from 'react';
import type { AgentProfile } from '../types/agent';

const agentColors: Record<string, string> = {
  equipment_monitor: '#722ed1',
  quality_inspector: '#eb2f96',
  production_scheduler: '#fa8c16',
};

const agentIcons: Record<string, string> = {
  equipment_monitor: '🔧',
  quality_inspector: '🔍',
  production_scheduler: '📊',
};

interface Props {
  onSwitchAgent: (agentName: string) => void;
}

export default function SessionList({ onSwitchAgent }: Props) {
  const chatStore = useChatStore();
  const authStore = useAuthStore();
  const [agents, setAgents] = useState<AgentProfile[]>([]);

  useEffect(() => {
    listAgents().then((res) => setAgents(res.agents)).catch(() => {});
  }, []);

  const handleSessionClick = async (sessionId: string) => {
    await chatStore.loadSessionMessages(authStore.userId, sessionId);
  };

  const handleNewSession = () => {
    chatStore.startNewSession();
  };

  const handleAgentClick = (agentName: string) => {
    onSwitchAgent(agentName);
  };

  return (
    <div style={{ width: 220, background: '#f5f5f5', borderRight: '1px solid #e8e8e8', padding: 12, height: '100%', overflowY: 'auto' }}>
      <div style={{ fontSize: 12, color: '#999', marginBottom: 8 }}>会话列表</div>
      {chatStore.sessions.map((session) => (
        <div
          key={session.id}
          onClick={() => handleSessionClick(session.id)}
          style={{
            background: '#fff',
            borderRadius: 6,
            padding: '8px 12px',
            marginBottom: 6,
            cursor: 'pointer',
            borderLeft: session.id === chatStore.currentSessionId ? '3px solid #1890ff' : 'none',
          }}
        >
          <div style={{ fontSize: 13, fontWeight: session.id === chatStore.currentSessionId ? 500 : 400 }}>{session.title}</div>
          <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>{session.lastMessageTime}</div>
        </div>
      ))}
      <div
        onClick={handleNewSession}
        style={{ border: '1px dashed #d9d9d9', borderRadius: 6, padding: '8px 12px', textAlign: 'center', color: '#999', fontSize: 13, cursor: 'pointer', marginTop: 8 }}
      >
        + 新会话
      </div>

      <div style={{ marginTop: 20, paddingTop: 12, borderTop: '1px solid #e8e8e8' }}>
        <div style={{ fontSize: 12, color: '#999', marginBottom: 8 }}>专家智能体</div>
        {agents.map((agent) => (
          <div
            key={agent.name}
            onClick={() => handleAgentClick(agent.name)}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 6, background: '#fff', borderRadius: 6, marginBottom: 4, fontSize: 12, cursor: 'pointer' }}
          >
            <span style={{ background: agentColors[agent.name] || '#1890ff', color: '#fff', padding: '2px 6px', borderRadius: 4, fontSize: 10 }}>
              {agentIcons[agent.name] || '🤖'}
            </span>
            {agent.display_name}
          </div>
        ))}
      </div>
    </div>
  );
}