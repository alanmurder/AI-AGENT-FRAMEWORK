import type { Message } from '../types/chat';
import ReactMarkdown from 'react-markdown';
import ProcessTimeline from './ProcessTimeline';

interface ChatBubbleProps {
  message: Message;
}

export default function ChatBubble({ message }: ChatBubbleProps) {
  const isHuman = message.type === 'human';

  return (
    <div style={{ display: 'flex', justifyContent: isHuman ? 'flex-end' : 'flex-start', marginBottom: 16 }}>
      <div
        style={{
          background: isHuman ? '#1890ff' : '#fff',
          color: isHuman ? '#fff' : '#333',
          padding: '10px 16px',
          borderRadius: 12,
          maxWidth: '70%',
          fontSize: 14,
          border: isHuman ? 'none' : '1px solid #e8e8e8',
          wordBreak: 'break-word',
        }}
      >
        {!isHuman && <ProcessTimeline events={message.process_events} />}
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
    </div>
  );
}
