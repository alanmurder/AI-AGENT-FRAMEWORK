import { Checkbox, Space, Typography } from 'antd';
import type { RoleMCPToolInfo } from '../types/api';

const { Text } = Typography;

interface Props {
  tools: RoleMCPToolInfo[];
  selected: string[];
  onChange: (selected: string[]) => void;
  loading?: boolean;
}

export default function MCPToolSelector({ tools, selected, onChange, loading }: Props) {
  if (loading) return <Text type="secondary">加载中...</Text>;
  if (!tools.length) return <Text type="secondary">当前角色无可用的 MCP 工具</Text>;

  const options = tools.map((t) => ({
    label: (
      <Space direction="vertical" size={0}>
        <Text strong>{t.name}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          [{t.server_name}] {t.description}
        </Text>
      </Space>
    ),
    value: t.name,
    disabled: !t.allowed,
  }));

  return (
    <Checkbox.Group
      options={options}
      value={selected}
      onChange={(vals) => onChange(vals as string[])}
      style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
    />
  );
}
