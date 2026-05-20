import { Table, Button, message, Statistic, Row, Col, Card } from 'antd';
import { useAdminStore } from '../store/adminStore';
import { useEffect } from 'react';

export default function ApprovalTable() {
  const store = useAdminStore();

  useEffect(() => {
    store.loadPendingApprovals();
  }, []);

  const columns = [
    { title: '审批ID', dataIndex: 'approval_id', key: 'id', render: (id: string) => <span style={{ color: '#1890ff', fontFamily: 'monospace' }}>{id}</span> },
    { title: '原因', dataIndex: 'reason', key: 'reason', render: (text: string) => <span style={{ color: '#ff4d4f' }}>{text}</span> },
    { title: '详情', dataIndex: 'details', key: 'details', ellipsis: true },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: any, record: any) => (
        <span>
          <Button type="primary" size="small" style={{ background: '#52c41a', marginRight: 4 }} onClick={() => { store.approve(record.approval_id).then(() => message.success('已批准')); }}>批准</Button>
          <Button danger size="small" onClick={() => { store.reject(record.approval_id).then(() => message.success('已拒绝')); }}>拒绝</Button>
        </span>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={12} style={{ marginBottom: 20 }}>
        <Col span={6}><Card><Statistic title="待审批" value={store.pendingApprovals.length} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
      </Row>
      <Table dataSource={store.pendingApprovals} columns={columns} rowKey="approval_id" pagination={false} />
    </div>
  );
}