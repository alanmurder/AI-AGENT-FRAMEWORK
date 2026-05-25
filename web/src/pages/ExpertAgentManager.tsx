import { useState, useEffect, useCallback } from 'react';
import {
  Button, Card, Col, Form, Input, message, Modal, Row, Select, Space, Spin, Tag, Typography, Divider, InputNumber,
} from 'antd';
import { PlusOutlined, DeleteOutlined, LinkOutlined } from '@ant-design/icons';
import { useExpertAgentStore } from '../store/expertAgentStore';
import SkillSelector from '../components/SkillSelector';
import MCPToolSelector from '../components/MCPToolSelector';
import type { AgentProfile } from '../types/agent';
import type { UserRole, AgentEndpointRequest, TestConnectionResult } from '../types/api';

const { Text } = Typography;
const { TextArea } = Input;

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'admin', label: 'admin - 系统管理员' },
  { value: 'manager', label: 'manager - 管理者' },
  { value: 'operator', label: 'operator - 操作员' },
  { value: 'viewer', label: 'viewer - 查看者' },
];

const PROTOCOL_OPTIONS = [
  { value: 'openai-chat', label: 'OpenAI Chat (兼容 API)' },
  { value: 'simple-json', label: 'Simple JSON (通用 REST)' },
];

const AUTH_OPTIONS = [
  { value: 'none', label: '无认证' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'header', label: '自定义 Header' },
];

const EMPTY_ENDPOINT: AgentEndpointRequest = {
  url: '',
  protocol: 'openai-chat',
  method: 'POST',
  auth_type: 'none',
  auth_credential: '',
  auth_header_name: 'Authorization',
  timeout_seconds: 120,
  headers: {},
};

interface AgentFormData {
  name: string;
  display_name: string;
  description: string;
  role: UserRole;
  type: string;
  soul_content: string;
  skills: string[];
  mcp_tools: string[];
  model_preference: string;
  max_context_tokens: number;
  endpoint: AgentEndpointRequest;
}

const EMPTY_FORM: AgentFormData = {
  name: '',
  display_name: '',
  description: '',
  role: 'operator',
  type: 'internal',
  soul_content: '',
  skills: [],
  mcp_tools: [],
  model_preference: 'primary',
  max_context_tokens: 32000,
  endpoint: { ...EMPTY_ENDPOINT },
};

export default function ExpertAgentManager() {
  const store = useExpertAgentStore();
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [formData, setFormData] = useState<AgentFormData>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
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
      const agent = data.agent;
      setFormData({
        name: agent.name,
        display_name: agent.display_name,
        description: agent.description,
        role: agent.role as UserRole,
        type: agent.type || 'internal',
        soul_content: data.soul_content || '',
        skills: agent.skills || [],
        mcp_tools: agent.mcp_tools || [],
        model_preference: agent.model_preference || 'primary',
        max_context_tokens: agent.max_context_tokens || 32000,
        endpoint: agent.endpoint ? { ...EMPTY_ENDPOINT, ...agent.endpoint } : { ...EMPTY_ENDPOINT },
      });
      if (agent.type !== 'external') {
        await loadRoleResources(agent.role);
      }
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

  const handleTypeChange = useCallback((type: string) => {
    setFormData((prev) => ({
      ...prev,
      type,
      skills: type === 'external' ? [] : prev.skills,
      mcp_tools: type === 'external' ? [] : prev.mcp_tools,
      soul_content: type === 'external' ? '' : prev.soul_content,
      endpoint: type === 'external' ? { ...EMPTY_ENDPOINT } : { ...EMPTY_ENDPOINT },
    }));
  }, []);

  const handleSave = useCallback(async () => {
    if (!formData.name || !formData.display_name) {
      message.warning('请填写名称和显示名称');
      return;
    }
    if (formData.type === 'external') {
      if (!formData.endpoint.url) {
        message.warning('外部智能体请填写端点 URL');
        return;
      }
    }
    setSaving(true);
    try {
      const payload = {
        name: formData.name,
        display_name: formData.display_name,
        description: formData.description,
        role: formData.role,
        type: formData.type,
        soul_content: formData.soul_content,
        skills: formData.skills,
        mcp_tools: formData.mcp_tools,
        model_preference: formData.model_preference,
        max_context_tokens: formData.max_context_tokens,
        endpoint: formData.type === 'external' ? formData.endpoint : undefined,
      };

      if (isNew) {
        await store.createAgent(payload);
        message.success('智能体创建成功');
        setIsNew(false);
        setSelectedAgent(formData.name);
      } else if (selectedAgent) {
        await store.updateAgent(selectedAgent, payload);
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

  const handleTestConnection = useCallback(async () => {
    if (!selectedAgent) return;
    setTesting(true);
    const { testAgentConnection } = await import('../api/expert-agents');
    try {
      const result: TestConnectionResult = await testAgentConnection(selectedAgent);
      if (result.reachable) {
        message.success(`连接成功! HTTP ${result.status_code} — ${result.response_preview?.substring(0, 100) || ''}`);
      } else {
        message.error(`连接失败: ${result.error || '未知错误'}`);
      }
    } catch {
      message.error('连接测试失败');
    } finally {
      setTesting(false);
    }
  }, [selectedAgent]);

  const selectedProfile: AgentProfile | undefined = store.agents.find((a) => a.name === selectedAgent);
  const isExternal = formData.type === 'external';

  const updateEndpoint = (key: keyof AgentEndpointRequest, value: unknown) => {
    setFormData((prev) => ({ ...prev, endpoint: { ...prev.endpoint, [key]: value } }));
  };

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
                      <Tag color={agent.type === 'external' ? 'orange' : (agent.source === 'api' ? 'green' : 'default')}>
                        {agent.type === 'external' ? '外部' : (agent.source === 'api' ? '配置' : '文件')}
                      </Tag>
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
            <Space>
              {selectedAgent && selectedProfile?.type === 'external' && (
                <Button size="small" icon={<LinkOutlined />} loading={testing} onClick={handleTestConnection}>
                  测试连接
                </Button>
              )}
              {selectedAgent && selectedProfile?.source === 'api' && (
                <Button danger size="small" icon={<DeleteOutlined />} onClick={handleDelete}>删除</Button>
              )}
            </Space>
          }
        >
          {(selectedAgent || isNew) ? (
            <Form layout="vertical" size="small">
              <Row gutter={16}>
                <Col span={6}>
                  <Form.Item label="名称 (name)" required>
                    <Input
                      value={formData.name}
                      onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
                      disabled={!isNew}
                      placeholder="英文标识"
                    />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item label="显示名称" required>
                    <Input
                      value={formData.display_name}
                      onChange={(e) => setFormData((p) => ({ ...p, display_name: e.target.value }))}
                      placeholder="如 设备分析专家"
                    />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item label="角色权限" required>
                    <Select value={formData.role} onChange={handleRoleChange} options={ROLE_OPTIONS} />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item label="类型" required>
                    <Select
                      value={formData.type}
                      onChange={handleTypeChange}
                      disabled={!isNew}
                      options={[
                        { value: 'internal', label: '配置型 (平台组装)' },
                        { value: 'external', label: '外部接入 (代理转发)' },
                      ]}
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

              <Divider style={{ margin: '12px 0' }} />

              {isExternal ? (
                <>
                  <Text strong style={{ color: '#1677ff' }}>外部端点配置</Text>
                  <Row gutter={16} style={{ marginTop: 8 }}>
                    <Col span={16}>
                      <Form.Item label="端点 URL" required>
                        <Input
                          value={formData.endpoint.url}
                          onChange={(e) => updateEndpoint('url', e.target.value)}
                          placeholder="http://workflow-engine:8080/api/v1/chat"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label="协议">
                        <Select
                          value={formData.endpoint.protocol}
                          onChange={(v) => updateEndpoint('protocol', v)}
                          options={PROTOCOL_OPTIONS}
                        />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Row gutter={16}>
                    <Col span={6}>
                      <Form.Item label="请求方法">
                        <Select
                          value={formData.endpoint.method}
                          onChange={(v) => updateEndpoint('method', v)}
                          options={[
                            { value: 'POST', label: 'POST' },
                            { value: 'GET', label: 'GET' },
                          ]}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item label="超时 (秒)">
                        <InputNumber
                          value={formData.endpoint.timeout_seconds}
                          onChange={(v) => updateEndpoint('timeout_seconds', v || 120)}
                          min={5}
                          max={600}
                          style={{ width: '100%' }}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item label="认证方式">
                        <Select
                          value={formData.endpoint.auth_type}
                          onChange={(v) => updateEndpoint('auth_type', v)}
                          options={AUTH_OPTIONS}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item label={formData.endpoint.auth_type === 'header' ? 'Header 名称' : '认证凭据'}>
                        <Input.Password
                          value={formData.endpoint.auth_type === 'header'
                            ? formData.endpoint.auth_header_name
                            : formData.endpoint.auth_credential}
                          onChange={(e) => updateEndpoint(
                            formData.endpoint.auth_type === 'header' ? 'auth_header_name' : 'auth_credential',
                            e.target.value,
                          )}
                          placeholder={formData.endpoint.auth_type === 'none' ? '无需认证' : '${ENV_VAR} 或直接填写'}
                          disabled={formData.endpoint.auth_type === 'none'}
                        />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    认证凭据支持 <code>{'${ENV_VAR}'}</code> 占位符，运行时从环境变量解析，避免密钥明文存储。
                  </Text>
                </>
              ) : (
                <>
                  <Text strong style={{ color: '#1677ff' }}>配置型智能体设置</Text>
                  <Row gutter={16} style={{ marginTop: 8 }}>
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
                </>
              )}

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
