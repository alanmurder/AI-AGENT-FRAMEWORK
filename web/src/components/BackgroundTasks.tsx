import { Table, Tag } from 'antd';
import { useAdminStore } from '../store/adminStore';
import { useAuthStore } from '../store/authStore';
import { useEffect } from 'react';

const statusColors: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
};

export default function BackgroundTasks() {
  const store = useAdminStore();
  const authStore = useAuthStore();

  useEffect(() => {
    store.loadBackgroundTasks(authStore.userId);
  }, []);

  const columns = [
    { title: '任务ID', dataIndex: 'task_id', key: 'id' },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={statusColors[s]}>{s}</Tag> },
    { title: '结果', dataIndex: 'result', key: 'result', ellipsis: true },
    { title: '错误', dataIndex: 'error', key: 'error', render: (e: string | null) => e ? <span style={{ color: '#ff4d4f' }}>{e}</span> : '-' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created' },
  ];

  return <Table dataSource={store.backgroundTasks} columns={columns} rowKey="task_id" />;
}