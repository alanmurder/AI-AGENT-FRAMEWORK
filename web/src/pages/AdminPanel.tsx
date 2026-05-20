import { Tabs } from 'antd';
import ApprovalTable from '../components/ApprovalTable';
import SkillManager from '../components/SkillManager';
import CronManager from '../components/CronManager';
import BackgroundTasks from '../components/BackgroundTasks';
import MemoryViewer from '../components/MemoryViewer';
import TeamStatus from '../components/TeamStatus';
import RoleGuard from '../components/RoleGuard';

export default function AdminPanel() {
  const tabItems = [
    { key: 'approvals', label: '审批队列', children: <RoleGuard roles={['admin']}><ApprovalTable /></RoleGuard> },
    { key: 'skills', label: 'Skill管理', children: <RoleGuard roles={['admin', 'manager']}><SkillManager /></RoleGuard> },
    { key: 'crons', label: '定时任务', children: <RoleGuard roles={['admin', 'manager']}><CronManager /></RoleGuard> },
    { key: 'background', label: '后台任务', children: <BackgroundTasks /> },
    { key: 'memory', label: '记忆文件', children: <MemoryViewer /> },
    { key: 'teams', label: '团队状态', children: <RoleGuard roles={['admin', 'manager']}><TeamStatus /></RoleGuard> },
  ];

  return <Tabs items={tabItems} />;
}