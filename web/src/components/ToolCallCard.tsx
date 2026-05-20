import { Collapse } from 'antd';
import type { ToolCallInfo } from '../types/chat';

interface ToolCallCardProps {
  toolCall: ToolCallInfo;
}

export default function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const argsStr = JSON.stringify(toolCall.args, null, 2);

  return (
    <div style={{
      background: '#f0f5ff',
      border: '1px solid #d6e4ff',
      borderRadius: 8,
      padding: '8px 12px',
      marginBottom: 8,
    }}>
      <Collapse
        size="small"
        items={[
          {
            key: toolCall.id,
            label: <span style={{ color: '#1890ff', fontWeight: 500 }}>调用工具: {toolCall.name}</span>,
            children: (
              <pre style={{ margin: 0, fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                {argsStr}
              </pre>
            ),
          },
        ]}
        defaultActiveKey={[toolCall.id]}
      />
    </div>
  );
}