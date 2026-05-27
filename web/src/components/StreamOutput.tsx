import ReactMarkdown from 'react-markdown';
import { useChatStore } from '../store/chatStore';
import ProcessTimeline from './ProcessTimeline';

export default function StreamOutput() {
  const { streamingContent, isStreaming, activeProcessEvents } = useChatStore();

  if (!streamingContent && !isStreaming) return null;

  return (
    <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
      <div style={{
        background: '#fff',
        padding: '10px 16px',
        borderRadius: 12,
        maxWidth: '70%',
        fontSize: 14,
        border: '1px solid #e8e8e8',
        wordBreak: 'break-word',
      }}>
        <ProcessTimeline events={activeProcessEvents} />
        <ReactMarkdown>{streamingContent}</ReactMarkdown>
        {isStreaming && <span style={{ opacity: 0.5 }}>▌</span>}
      </div>
    </div>
  );
}
