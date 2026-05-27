import { Collapse, Space, Tag, Typography } from 'antd';
import type { ProcessEvent } from '../types/chat';

interface ProcessTimelineProps {
  events?: ProcessEvent[];
}

const { Text } = Typography;

function getSummary(events: ProcessEvent[]) {
  const skillCount = events
    .filter((event) => event.type === 'skill_manifest')
    .reduce((count, event) => count + event.skills.length, 0);
  const skillUseCount = events.filter((event) => event.type === 'skill_use').length;
  const toolCount = events.filter((event) => event.type === 'tool_call').length;

  return { skillCount, skillUseCount, toolCount };
}

function renderEvent(event: ProcessEvent) {
  if (event.type === 'skill_manifest') {
    return (
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <Text strong>Loaded Skills</Text>
        <Space size={[4, 4]} wrap>
          {event.skills.map((skill) => (
            <Tag key={skill.name}>{skill.name}</Tag>
          ))}
        </Space>
      </Space>
    );
  }

  if (event.type === 'skill_use') {
    return (
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <Space size={6} wrap>
          <Text strong>Using Skill</Text>
          <Tag color="blue">Skill: {event.name}</Tag>
          {event.phase && <Tag>{event.phase}</Tag>}
        </Space>
        {event.reason && <Text type="secondary">{event.reason}</Text>}
      </Space>
    );
  }

  if (event.type === 'tool_call') {
    return (
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <Space size={6} wrap>
          <Text strong>Tool Call</Text>
          <Tag color="geekblue">{event.name}</Tag>
        </Space>
        <pre style={{ margin: 0, fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
          {JSON.stringify(event.args, null, 2)}
        </pre>
      </Space>
    );
  }

  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Text strong>{event.content || event.stage || 'Progress'}</Text>
      {event.content && event.stage && event.content !== event.stage && <Text type="secondary">{event.stage}</Text>}
    </Space>
  );
}

export default function ProcessTimeline({ events }: ProcessTimelineProps) {
  if (!events || events.length === 0) return null;

  const { skillCount, skillUseCount, toolCount } = getSummary(events);

  return (
    <div style={{ marginBottom: 8 }}>
      <Collapse
        size="small"
        items={[
          {
            key: 'process',
            label: (
              <Space size={6} wrap>
                <Text strong>Process</Text>
                <Tag>{skillCount} Skills</Tag>
                <Tag>{skillUseCount} Skill use</Tag>
                <Tag>{toolCount} Tool</Tag>
              </Space>
            ),
            children: (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                {events.map((event) => (
                  <div key={event.id}>{renderEvent(event)}</div>
                ))}
              </Space>
            ),
          },
        ]}
      />
    </div>
  );
}
