import { Checkbox, Space, Typography } from 'antd';
import type { RoleSkillInfo } from '../types/api';

const { Text } = Typography;

interface Props {
  skills: RoleSkillInfo[];
  selected: string[];
  onChange: (selected: string[]) => void;
  loading?: boolean;
}

export default function SkillSelector({ skills, selected, onChange, loading }: Props) {
  if (loading) return <Text type="secondary">加载中...</Text>;
  if (!skills.length) return <Text type="secondary">当前角色无可用的 Skill</Text>;

  const options = skills.map((s) => ({
    label: (
      <Space direction="vertical" size={0}>
        <Text strong>{s.name}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>{s.description}</Text>
      </Space>
    ),
    value: s.name,
    disabled: !s.allowed,
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
