import { Table, Tag, Card, List } from 'antd';
import { useEffect, useState } from 'react';
import { listTeams } from '../api/agents';
import { getAgentTasks } from '../api/agents';
import type { TeamConfig, TaskItem } from '../types/agent';

const taskStatusColors: Record<string, string> = {
  PENDING: 'default',
  CLAIMED: 'processing',
  RUNNING: 'processing',
  COMPLETED: 'success',
  FAILED: 'error',
  BLOCKED: 'warning',
};

export default function TeamStatus() {
  const [teams, setTeams] = useState<TeamConfig[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);

  useEffect(() => {
    listTeams().then((res) => {
      setTeams(res.teams);
      if (res.teams.length > 0) {
        getAgentTasks(res.teams[0].name).then((res2) => setTasks(res2.tasks));
      }
    });
  }, []);

  const taskColumns = [
    { title: '任务ID', dataIndex: 'task_id', key: 'id' },
    { title: '描述', dataIndex: 'description', key: 'desc', ellipsis: true },
    { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={taskStatusColors[s]}>{s}</Tag> },
    { title: '执行人', dataIndex: 'assignee', key: 'assignee' },
    { title: '结果', dataIndex: 'result', key: 'result', ellipsis: true },
  ];

  return (
    <div>
      <Card title="团队列表" style={{ marginBottom: 16 }}>
        <List
          dataSource={teams}
          renderItem={(team) => (
            <List.Item>
              <List.Item.Meta title={team.display_name} description={`队长: ${team.captain} | 成员: ${team.members.join(', ')}`} />
            </List.Item>
          )}
        />
      </Card>
      <Card title="TaskBoard 任务状态">
        <Table dataSource={tasks} columns={taskColumns} rowKey="task_id" pagination={false} />
      </Card>
    </div>
  );
}