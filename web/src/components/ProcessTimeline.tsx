import { Collapse, Space, Tag, Typography } from 'antd';
import type { CSSProperties } from 'react';
import type { ProcessEvent } from '../types/chat';

interface ProcessTimelineProps {
  events?: ProcessEvent[];
}

const { Text } = Typography;

const wrapStyle: CSSProperties = {
  maxWidth: '100%',
  overflowWrap: 'anywhere',
  wordBreak: 'break-word',
  whiteSpace: 'normal',
};

const argsStyle: CSSProperties = {
  margin: 0,
  fontSize: 12,
  fontFamily: 'monospace',
  maxWidth: '100%',
  overflowX: 'auto',
  overflowWrap: 'anywhere',
  wordBreak: 'break-word',
  whiteSpace: 'pre-wrap',
};

function getSummary(events: ProcessEvent[]) {
  const loadedSkills = new Set<string>();

  events.forEach((event) => {
    if (event.type === 'skill_manifest') {
      event.skills.forEach((skill) => loadedSkills.add(skill.name));
    }
  });

  const skillCount = loadedSkills.size;
  const skillUseCount = events.filter((event) => event.type === 'skill_use').length;
  const toolCount = events.filter((event) => event.type === 'tool_call').length;
  const progressCount = events.filter((event) => event.type === 'progress').length;

  return { skillCount, skillUseCount, toolCount, progressCount };
}

function formatCount(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function renderEvent(event: ProcessEvent) {
  if (event.type === 'skill_manifest') {
    return (
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <Text strong>Loaded Skills</Text>
        <Space size={[4, 4]} wrap>
          {event.skills.map((skill) => (
            <Tag key={skill.name} style={wrapStyle}>
              {skill.name}
            </Tag>
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
          <Tag color="blue" style={wrapStyle}>
            Skill: {event.name}
          </Tag>
          {event.phase && <Tag style={wrapStyle}>{event.phase}</Tag>}
        </Space>
        {event.reason && (
          <Text type="secondary" style={wrapStyle}>
            {event.reason}
          </Text>
        )}
      </Space>
    );
  }

  if (event.type === 'tool_call') {
    return (
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <Space size={6} wrap>
          <Text strong>Tool Call</Text>
          <Tag color="geekblue" style={wrapStyle}>
            {event.name}
          </Tag>
        </Space>
        <pre style={argsStyle}>{JSON.stringify(event.args, null, 2)}</pre>
      </Space>
    );
  }

  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Text strong style={wrapStyle}>
        {event.content || event.stage || 'Progress'}
      </Text>
      {event.content && event.stage && event.content !== event.stage && (
        <Text type="secondary" style={wrapStyle}>
          {event.stage}
        </Text>
      )}
    </Space>
  );
}

export default function ProcessTimeline({ events }: ProcessTimelineProps) {
  if (!events || events.length === 0) return null;

  const { skillCount, skillUseCount, toolCount, progressCount } = getSummary(events);
  const summaryItems = [
    skillCount > 0 ? formatCount(skillCount, 'Skill') : null,
    skillUseCount > 0 ? formatCount(skillUseCount, 'Skill use', 'Skill uses') : null,
    toolCount > 0 ? formatCount(toolCount, 'Tool') : null,
    progressCount > 0 ? formatCount(progressCount, 'Progress', 'Progress') : null,
  ].filter((item): item is string => Boolean(item));

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
                {summaryItems.map((item) => (
                  <Tag key={item}>{item}</Tag>
                ))}
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
