import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import AgentMarket from './pages/AgentMarket';
import AdminPanel from './pages/AdminPanel';
import RoleGuard from './components/RoleGuard';
import { useAuthStore } from './store/authStore';

function AuthRedirect() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return isAuthenticated ? <Navigate to="/chat" /> : <Navigate to="/login" />;
}

function ProtectedLayout() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return isAuthenticated ? <AppLayout /> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<AuthRedirect />} />
        <Route element={<ProtectedLayout />}>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agents" element={<AgentMarket />} />
          <Route path="/admin" element={<RoleGuard roles={['admin', 'manager']}><AdminPanel /></RoleGuard>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
