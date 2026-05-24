import { useState, useEffect, useCallback } from 'react';
import {
  Button, Card, Col, Form, Input, message, Modal, Row, Select, Space, Spin, Tag, Typography,
} from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useExpertAgentStore } from '../store/expertAgentStore';
import SkillSelector from '../components/SkillSelector';
import MCPToolSelector from '../components/MCPToolSelector';
import type { AgentProfile } from '../types/agent';
import type { UserRole } from '../types/api';

const { Text } = Typography;
const { TextArea } = Input;

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'admin', label: 'admin - 系统管理员' },
  { value: 'manager', label: 'manager - 管理者' },
  { value: 'operator', label: 'operator - 操作员' },
  { value: 'viewer', label: 'viewer - 查看者' },
];

interface AgentFormData {
  name: string;
  display_name: string;
  description: string;
  role: UserRole;
  soul_content: string;
  skills: string[];
  mcp_tools: string[];
  model_preference: string;
  max_context_tokens: number;
}

const EMPTY_FORM: AgentFormData = {
  name: '',
  display_name: '',
  description: '',
  role: 'operator',
  soul_content: '',
  skills: [],
  mcp_tools: [],
  model_preference: 'primary',
  max_context_tokens: 32000,
};

export default function ExpertAgentManager() {
  const store = useExpertAgentStore();
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [formData, setFormData] = useState<AgentFormData>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [isNew, setIsNew] = useState(false);

  useEffect(() => {
    store.loadAgents();
  }, []);

  const loadRoleResources = useCallback(async (role: string) => {
    await Promise.all([
      store.loadRoleSkills(role),
      store.loadRoleMCPTools(role),
    ]);
  }, [store]);

  const selectAgent = useCallback(async (name: string) => {
    setSelectedAgent(name);
    setIsNew(false);
    const { getAgent } = await import('../api/expert-agents');
    try {
      const data = await getAgent(name);
      setFormData({
        name: data.agent.name,
        display_name: data.agent.display_name,
        description: data.agent.description,
        role: data.agent.role as UserRole,
        soul_content: data.soul_content || '',
        skills: data.agent.skills || [],
        mcp_tools: data.agent.mcp_tools || [],
        model_preference: data.agent.model_preference || 'primary',
        max_context_tokens: data.agent.max_context_tokens || 32000,
      });
      await loadRoleResources(data.agent.role);
    } catch {
      message.error('加载智能体详情失败');
    }
  }, [loadRoleResources]);

  const newAgent = useCallback(() => {
    setSelectedAgent(null);
    setIsNew(true);
    setFormData(EMPTY_FORM);
  }, []);

  const handleRoleChange = useCallback((role: UserRole) => {
    setFormData((prev) => ({ ...prev, role, skills: [], mcp_tools: [] }));
    loadRoleResources(role);
  }, [loadRoleResources]);

  const handleSave = useCallback(async () => {
    if (!formData.name || !formData.display_name) {
      message.warning('请填写名称和显示名称');
      return;
    }
    setSaving(true);
    try {
      if (isNew) {
        await store.createAgent({
          name: formData.name,
          display_name: formData.display_name,
          description: formData.description,
          soul_content: formData.soul_content,
          role: formData.role,
          skills: formData.skills,
          mcp_tools: formData.mcp_tools,
          model_preference: formData.model_preference,
          max_context_tokens: formData.max_context_tokens,
        });
        message.success('智能体创建成功');
        setIsNew(false);
        setSelectedAgent(formData.name);
      } else if (selectedAgent) {
        await store.updateAgent(selectedAgent, {
          display_name: formData.display_name,
          description: formData.description,
          soul_content: formData.soul_content,
          role: formData.role,
          skills: formData.skills,
          mcp_tools: formData.mcp_tools,
          model_preference: formData.model_preference,
          max_context_tokens: formData.max_context_tokens,
        });
        message.success('智能体更新成功');
      }
      await store.loadAgents();
    } catch {
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  }, [formData, isNew, selectedAgent, store]);

  const handleDelete = useCallback(async () => {
    if (!selectedAgent) return;
    const agent = store.agents.find((a) => a.name === selectedAgent);
    if (agent?.source === 'file') {
      message.warning('无法删除文件系统中的智能体，请直接删除 profile.yaml');
      return;
    }
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除智能体 "${selectedAgent}" 吗？此操作不可撤销。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await store.deleteAgent(selectedAgent);
        message.success('智能体已删除');
        setSelectedAgent(null);
        setIsNew(false);
        setFormData(EMPTY_FORM);
        await store.loadAgents();
      },
    });
  }, [selectedAgent, store]);

  const selectedProfile: AgentProfile | undefined = store.agents.find((a) => a.name === selectedAgent);

  return (
    <Row gutter={16}>
      <Col span={6}>
        <Card
          title="专家智能体"
          size="small"
          extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={newAgent}>创建</Button>}
        >
          <Spin spinning={store.loading}>
            <div style={{ maxHeight: 500, overflow: 'auto' }}>
              {store.agents.map((agent) => (
                <Card
                  key={agent.name}
                  size="small"
                  hoverable
                  style={{ marginBottom: 8, borderColor: selectedAgent === agent.name ? '#1677ff' : undefined }}
                  onClick={() => selectAgent(agent.name)}
                >
                  <Space direction="vertical" size={0}>
                    <Text strong>{agent.display_name}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>{agent.name}</Text>
                    <Space size={4}>
                      <Tag color="blue">{agent.role}</Tag>
                      <Tag color={agent.source === 'api' ? 'green' : 'default'}>{agent.source === 'api' ? 'API' : '文件'}</Tag>
                    </Space>
                  </Space>
                </Card>
              ))}
              {!store.agents.length && <Text type="secondary">暂无可管理的智能体</Text>}
            </div>
          </Spin>
        </Card>
      </Col>

      <Col span={18}>
        <Card
          title={isNew ? '创建专家智能体' : (selectedProfile?.display_name || '选择智能体')}
          size="small"
          extra={
            selectedAgent && selectedProfile?.source === 'api' && (
              <Button danger size="small" icon={<DeleteOutlined />} onClick={handleDelete}>删除</Button>
            )
          }
        >
          {(selectedAgent || isNew) ? (
            <Form layout="vertical" size="small">
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label="名称 (name)" required>
                    <Input
                      value={formData.name}
                      onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
                      disabled={!isNew}
                      placeholder="英文标识，如 equipment_analyzer"
                    />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="显示名称" required>
                    <Input
                      value={formData.display_name}
                      onChange={(e) => setFormData((p) => ({ ...p, display_name: e.target.value }))}
                      placeholder="如 设备分析专家"
                    />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="角色权限" required>
                    <Select
                      value={formData.role}
                      onChange={handleRoleChange}
                      options={ROLE_OPTIONS}
                    />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item label="描述">
                <Input
                  value={formData.description}
                  onChange={(e) => setFormData((p) => ({ ...p, description: e.target.value }))}
                  placeholder="简要描述智能体的能力和用途"
                />
              </Form.Item>

              <Row gutter={16}>
                <Col span={6}>
                  <Form.Item label="模型偏好">
                    <Select
                      value={formData.model_preference}
                      onChange={(v) => setFormData((p) => ({ ...p, model_preference: v }))}
                      options={[
                        { value: 'primary', label: 'Primary (主模型)' },
                        { value: 'mini', label: 'Mini (轻量模型)' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item label="最大上下文 Token">
                    <Input
                      type="number"
                      value={formData.max_context_tokens}
                      onChange={(e) => setFormData((p) => ({ ...p, max_context_tokens: Number(e.target.value) }))}
                    />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item label="Soul 内容 (系统提示词)">
                <TextArea
                  rows={8}
                  value={formData.soul_content}
                  onChange={(e) => setFormData((p) => ({ ...p, soul_content: e.target.value }))}
                  placeholder="编写智能体的系统提示词，定义其角色、专业知识、行为准则..."
                  style={{ fontFamily: 'monospace' }}
                />
              </Form.Item>

              <Row gutter={16}>
                <Col span={12}>
                  <Card title="Skills" size="small" style={{ marginBottom: 16 }}>
                    <SkillSelector
                      skills={store.roleSkills}
                      selected={formData.skills}
                      onChange={(v) => setFormData((p) => ({ ...p, skills: v }))}
                      loading={store.loading}
                    />
                  </Card>
                </Col>
                <Col span={12}>
                  <Card title="MCP 工具" size="small" style={{ marginBottom: 16 }}>
                    <MCPToolSelector
                      tools={store.roleMCPTools}
                      selected={formData.mcp_tools}
                      onChange={(v) => setFormData((p) => ({ ...p, mcp_tools: v }))}
                      loading={store.loading}
                    />
                  </Card>
                </Col>
              </Row>

              <Space>
                <Button type="primary" onClick={handleSave} loading={saving}>
                  {isNew ? '创建' : '保存'}
                </Button>
                <Button onClick={() => { setIsNew(false); setSelectedAgent(null); }}>
                  取消
                </Button>
              </Space>
            </Form>
          ) : (
            <Text type="secondary">从左侧列表选择一个智能体或点击"创建"新建</Text>
          )}
        </Card>
      </Col>
    </Row>
  );
}
