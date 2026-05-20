import type { ReactNode } from 'react';
import { Result } from 'antd';
import { useAuth } from '../hooks/useAuth';
import type { UserRole } from '../types/api';

interface RoleGuardProps {
  roles: UserRole[];
  children: ReactNode;
}

export default function RoleGuard({ roles, children }: RoleGuardProps) {
  const { role } = useAuth();

  if (!roles.includes(role)) {
    return (
      <Result
        status="403"
        title="权限不足"
        subTitle={`需要 ${roles.join('/')} 角色，当前角色: ${role}`}
      />
    );
  }

  return <>{children}</>;
}