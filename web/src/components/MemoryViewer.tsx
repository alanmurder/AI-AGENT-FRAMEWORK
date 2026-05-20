import { Tabs, Card } from 'antd';
import ReactMarkdown from 'react-markdown';
import { useAuthStore } from '../store/authStore';
import { useState, useEffect } from 'react';
import { getMemoryFile } from '../api/memory';

export default function MemoryViewer() {
  const authStore = useAuthStore();
  const [activeTab, setActiveTab] = useState('MEMORY.md');
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getMemoryFile(authStore.userId, activeTab)
      .then((res) => setContent(res.content))
      .catch(() => setContent('加载失败'))
      .finally(() => setLoading(false));
  }, [activeTab]);

  return (
    <Card loading={loading}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'SOUL.md', label: 'SOUL' },
          { key: 'USER.md', label: 'USER' },
          { key: 'MEMORY.md', label: 'MEMORY' },
        ]}
      />
      <div style={{ padding: 16, background: '#fafafa', borderRadius: 8, minHeight: 200 }}>
        <ReactMarkdown>{content || '(空)'}</ReactMarkdown>
      </div>
    </Card>
  );
}