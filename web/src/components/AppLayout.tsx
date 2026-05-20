import { Layout, Menu, Tag } from 'antd';
import { MessageOutlined, AppstoreOutlined, SettingOutlined } from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const { Header, Content } = Layout;

const roleColors: Record<string, string> = {
  admin: 'green',
  manager: 'blue',
  operator: 'orange',
  viewer: 'default',
};

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { userId, role, logout } = useAuth();

  const menuItems = [
    { key: '/chat', icon: <MessageOutlined />, label: '对话' },
    { key: '/agents', icon: <AppstoreOutlined />, label: '智能体广场' },
    { key: '/admin', icon: <SettingOutlined />, label: '管理后台' },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ color: '#fff', fontSize: 18, fontWeight: 'bold' }}>AI Agent Platform</div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, minWidth: 0 }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Tag color={roleColors[role]}>{role}</Tag>
          <span style={{ color: '#fff' }}>{userId}</span>
          <a style={{ color: '#fff', fontSize: 13 }} onClick={logout}>退出</a>
        </div>
      </Header>
      <Content>
        <Outlet />
      </Content>
    </Layout>
  );
}