import { Table, Button, Form, Input, Modal, message } from 'antd';
import { useAdminStore } from '../store/adminStore';
import { useAuthStore } from '../store/authStore';
import { useEffect, useState } from 'react';

export default function CronManager() {
  const store = useAdminStore();
  const authStore = useAuthStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    store.loadCronTasks(authStore.userId);
  }, []);

  const handleCreate = async () => {
    const values = await form.validateFields();
    await store.createCronTask({ ...values, user_id: authStore.userId });
    message.success('定时任务已创建');
    setModalOpen(false);
    form.resetFields();
    store.loadCronTasks(authStore.userId);
  };

  const handleDelete = async (taskId: string) => {
    await store.deleteCronTask(taskId);
    message.success('定时任务已删除');
    store.loadCronTasks(authStore.userId);
  };

  const columns = [
    { title: '任务ID', dataIndex: 'task_id', key: 'id' },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: 'Cron表达式', dataIndex: 'cron_expression', key: 'cron' },
    { title: 'Prompt', dataIndex: 'prompt', key: 'prompt', ellipsis: true },
    { title: '状态', dataIndex: 'status', key: 'status' },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: any) => <Button danger size="small" onClick={() => handleDelete(record.task_id)}>删除</Button>,
    },
  ];

  return (
    <div>
      <Button type="primary" style={{ marginBottom: 16 }} onClick={() => setModalOpen(true)}>创建定时任务</Button>
      <Table dataSource={store.cronTasks} columns={columns} rowKey="task_id" />
      <Modal title="创建定时任务" open={modalOpen} onOk={handleCreate} onCancel={() => setModalOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="任务名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="cron_expression" label="Cron表达式" rules={[{ required: true }]}>
            <Input placeholder="*/5 * * * *" />
          </Form.Item>
          <Form.Item name="prompt" label="执行Prompt" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}