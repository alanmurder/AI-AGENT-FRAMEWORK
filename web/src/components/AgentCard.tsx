import { Button, Tag } from 'antd';
import type { AgentProfile } from '../types/agent';
import { useNavigate } from 'react-router-dom';

const roleTagColors: Record<string, string> = {
  operator: 'green',
  manager: 'orange',
  admin: 'green',
};

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

interface AgentCardProps {
  agent: AgentProfile;
}

export default function AgentCard({ agent }: AgentCardProps) {
  const navigate = useNavigate();

  const handleStart = () => {
    navigate(`/chat?agent=${agent.name}`);
  };

  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e8e8e8', padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <div style={{ width: 40, height: 40, background: agentColors[agent.name] || '#1890ff', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: '#fff' }}>
          {agentIcons[agent.name] || '🤖'}
        </div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600 }}>{agent.display_name}</div>
          <div style={{ fontSize: 12, color: '#999' }}>{agent.name}</div>
        </div>
      </div>
      <div style={{ fontSize: 13, color: '#666', marginBottom: 12, lineHeight: 1.6 }}>{agent.description}</div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        <Tag color="blue">{agent.skill_plugin}</Tag>
        <Tag color={roleTagColors[agent.role] || 'default'}>{agent.role}</Tag>
      </div>
      <Button type="primary" block onClick={handleStart}>开始对话</Button>
    </div>
  );
}