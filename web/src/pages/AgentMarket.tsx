import { useEffect, useState } from 'react';
import { listAgents } from '../api/agents';
import { listPlugins } from '../api/admin';
import AgentCard from '../components/AgentCard';
import type { AgentProfile } from '../types/agent';
import type { PluginInfo } from '../types/api';

export default function AgentMarket() {
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [activePlugin, setActivePlugin] = useState<string>('all');

  useEffect(() => {
    listAgents().then((res) => setAgents(res.agents));
    listPlugins().then((res) => setPlugins(res.plugins));
  }, []);

  const filteredAgents = activePlugin === 'all'
    ? agents
    : agents.filter((a) => a.skill_plugin === activePlugin);

  return (
    <div>
      {/* Hero banner */}
      <div style={{ background: 'linear-gradient(135deg, #1890ff, #722ed1)', padding: '24px 32px', color: '#fff' }}>
        <div style={{ fontSize: 20, fontWeight: 'bold' }}>专家智能体广场</div>
        <div style={{ fontSize: 14, marginTop: 8, opacity: 0.9 }}>选择专业领域的智能体，获取精准的行业知识与辅助决策</div>
      </div>

      {/* Plugin filter tabs */}
      <div style={{ padding: '12px 24px', display: 'flex', gap: 8, borderBottom: '1px solid #e8e8e8' }}>
        <button
          onClick={() => setActivePlugin('all')}
          style={{ background: activePlugin === 'all' ? '#1890ff' : '#f0f5ff', color: activePlugin === 'all' ? '#fff' : '#1890ff', border: activePlugin === 'all' ? 'none' : '1px solid #d6e4ff', padding: '6px 16px', borderRadius: 4, fontSize: 13, cursor: 'pointer' }}
        >全部</button>
        {plugins.map((p) => (
          <button
            key={p.name}
            onClick={() => setActivePlugin(p.name)}
            style={{ background: activePlugin === p.name ? '#1890ff' : '#fff', color: activePlugin === p.name ? '#fff' : '#666', border: activePlugin === p.name ? 'none' : '1px solid #d9d9d9', padding: '6px 16px', borderRadius: 4, fontSize: 13, cursor: 'pointer' }}
          >{p.description} ({p.name})</button>
        ))}
      </div>

      {/* Agent cards grid */}
      <div style={{ padding: '20px 24px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {filteredAgents.map((agent) => (
          <AgentCard key={agent.name} agent={agent} />
        ))}
      </div>
    </div>
  );
}