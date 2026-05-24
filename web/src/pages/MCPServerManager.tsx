import { useState, useEffect, useCallback } from 'react';
import {
  Button, Card, Col, Form, Input, message, Modal, Row, Select, Space, Spin, Switch, Tag, Typography,
} from 'antd';
import { PlusOutlined, DeleteOutlined, LinkOutlined, DisconnectOutlined } from '@ant-design/icons';
import { useMCPStore } from '../store/mcpStore';
import * as mcpApi from '../api/mcp';
import type { MCPServerConfig, MCPToolInfo } from '../types/api';

const { Text } = Typography;

const EMPTY_FORM: MCPServerConfig = {
  name: '',
  transport: 'stdio',
  command: '',
  args: [],
  url: '',
  enabled: true,
  env: {},
};

export default function MCPServerManager() {
  const store = useMCPStore();
  const [selectedServer, setSelectedServer] = useState<string | null>(null);
  const [formData, setFormData] = useState<MCPServerConfig>(EMPTY_FORM);
  const [serverTools, setServerTools] = useState<MCPToolInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [isNew, setIsNew] = useState(false);

  useEffect(() => {
    store.loadServers();
  }, []);

  const selectServer = useCallback(async (name: string) => {
    setSelectedServer(name);
    setIsNew(false);
    try {
      const data = await mcpApi.getMCPServer(name);
      setFormData(data.config);
      setServerTools(data.tools || []);
    } catch {
      message.error('加载 MCP 服务器详情失败');
    }
  }, []);

  const newServer = useCallback(() => {
    setSelectedServer(null);
    setIsNew(true);
    setFormData(EMPTY_FORM);
    setServerTools([]);
  }, []);

  const handleSave = useCallback(async () => {
    if (!formData.name) {
      message.warning('请填写服务器名称');
      return;
    }
    setSaving(true);
    try {
      if (isNew) {
        await store.createServer(formData);
        message.success('MCP 服务器创建成功');
        setIsNew(false);
        setSelectedServer(formData.name);
      } else if (selectedServer) {
        await store.updateServer(selectedServer, formData);
        message.success('MCP 服务器更新成功');
      }
      await store.loadServers();
    } catch {
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  }, [formData, isNew, selectedServer, store]);

  const handleDelete = useCallback(async () => {
    if (!selectedServer) return;
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除 MCP 服务器 "${selectedServer}" 吗？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await store.deleteServer(selectedServer);
        message.success('MCP 服务器已删除');
        setSelectedServer(null);
        setFormData(EMPTY_FORM);
        setServerTools([]);
        await store.loadServers();
      },
    });
  }, [selectedServer, store]);

  const handleConnect = useCallback(async () => {
    if (!selectedServer) return;
    setConnecting(true);
    try {
      const result = await store.connectServer(selectedServer);
      message.success(`已连接，发现 ${result.tools} 个工具`);
      const data = await mcpApi.getMCPServer(selectedServer);
      setServerTools(data.tools || []);
    } catch {
      message.error('连接失败');
    } finally {
      setConnecting(false);
    }
  }, [selectedServer, store]);

  const handleDisconnect = useCallback(async () => {
    if (!selectedServer) return;
    try {
      await store.disconnectServer(selectedServer);
      message.success('已断开连接');
      setServerTools([]);
    } catch {
      message.error('断开失败');
    }
  }, [selectedServer, store]);

  return (
    <Row gutter={16}>
      <Col span={6}>
        <Card
          title="MCP 服务器"
          size="small"
          extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={newServer}>添加</Button>}
        >
          <Spin spinning={store.loading}>
            <div style={{ maxHeight: 500, overflow: 'auto' }}>
              {store.servers.map((s) => (
                <Card
                  key={s.name}
                  size="small"
                  hoverable
                  style={{ marginBottom: 8, borderColor: selectedServer === s.name ? '#1677ff' : undefined }}
                  onClick={() => selectServer(s.name)}
                >
                  <Space direction="vertical" size={0}>
                    <Space>
                      <Text strong>{s.name}</Text>
                      <Tag color={s.enabled ? 'green' : 'default'}>{s.enabled ? '已启用' : '已禁用'}</Tag>
                    </Space>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {s.transport === 'stdio' ? `stdio: ${s.command}` : `sse: ${s.url}`}
                    </Text>
                  </Space>
                </Card>
              ))}
              {!store.servers.length && <Text type="secondary">暂无 MCP 服务器配置</Text>}
            </div>
          </Spin>
        </Card>
      </Col>

      <Col span={18}>
        <Card
          title={isNew ? '添加 MCP 服务器' : (selectedServer || '选择服务器')}
          size="small"
          extra={
            selectedServer && (
              <Space>
                <Button
                  size="small"
                  icon={<LinkOutlined />}
                  loading={connecting}
                  onClick={handleConnect}
                >
                  连接
                </Button>
                <Button
                  size="small"
                  icon={<DisconnectOutlined />}
                  onClick={handleDisconnect}
                >
                  断开
                </Button>
                <Button danger size="small" icon={<DeleteOutlined />} onClick={handleDelete}>删除</Button>
              </Space>
            )
          }
        >
          {(selectedServer || isNew) ? (
            <Form layout="vertical" size="small">
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="服务器名称" required>
                    <Input
                      value={formData.name}
                      onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
                      disabled={!isNew}
                      placeholder="如 filesystem, github"
                    />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item label="传输类型">
                    <Select
                      value={formData.transport}
                      onChange={(v) => setFormData((p) => ({ ...p, transport: v as 'stdio' | 'sse' }))}
                      options={[
                        { value: 'stdio', label: 'stdio (子进程)' },
                        { value: 'sse', label: 'SSE (HTTP)' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item label="启用">
                    <Switch
                      checked={formData.enabled}
                      onChange={(v) => setFormData((p) => ({ ...p, enabled: v }))}
                    />
                  </Form.Item>
                </Col>
              </Row>

              {formData.transport === 'stdio' ? (
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item label="命令">
                      <Input
                        value={formData.command}
                        onChange={(e) => setFormData((p) => ({ ...p, command: e.target.value }))}
                        placeholder="如 npx"
                      />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="参数 (逗号分隔)">
                      <Input
                        value={(formData.args || []).join(', ')}
                        onChange={(e) => setFormData((p) => ({
                          ...p,
                          args: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                        }))}
                        placeholder="如 -y, @modelcontextprotocol/server-filesystem"
                      />
                    </Form.Item>
                  </Col>
                </Row>
              ) : (
                <Form.Item label="SSE URL">
                  <Input
                    value={formData.url}
                    onChange={(e) => setFormData((p) => ({ ...p, url: e.target.value }))}
                    placeholder="http://localhost:3001/sse"
                  />
                </Form.Item>
              )}

              {serverTools.length > 0 && (
                <Card title={`已发现工具 (${serverTools.length})`} size="small" style={{ marginBottom: 16 }}>
                  {serverTools.map((t) => (
                    <Tag key={t.full_name} color="blue" style={{ marginBottom: 4 }}>
                      {t.full_name}
                    </Tag>
                  ))}
                </Card>
              )}

              <Space>
                <Button type="primary" onClick={handleSave} loading={saving}>
                  {isNew ? '创建' : '保存'}
                </Button>
                <Button onClick={() => { setIsNew(false); setSelectedServer(null); }}>
                  取消
                </Button>
              </Space>
            </Form>
          ) : (
            <Text type="secondary">从左侧列表选择一个 MCP 服务器或点击"添加"新建</Text>
          )}
        </Card>
      </Col>
    </Row>
  );
}
