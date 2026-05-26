import { Button, Card, message, Space, List, Spin, Upload } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import { useAdminStore } from '../store/adminStore';
import { useEffect, useState } from 'react';
import { verifySkill, optimizeSkill, triggerAutoEvolution, importSkillZip } from '../api/admin';

export default function SkillManager() {
  const store = useAdminStore();
  const [loading, setLoading] = useState<string>('');

  useEffect(() => {
    store.loadSkills();
  }, []);

  const handleVerify = async () => {
    setLoading('verify');
    try {
      const res = await verifySkill({ requirement: '示例Skill需求' });
      message.success(res.passed ? '验证通过' : '验证未通过');
    } catch { message.error('验证失败'); }
    finally { setLoading(''); }
  };

  const handleOptimize = async (skillName: string) => {
    setLoading('optimize');
    try {
      const res = await optimizeSkill(skillName);
      message.success(res.optimized ? `优化成功 (分数: ${res.best_candidate_score})` : '未发现更好变体');
    } catch { message.error('优化失败'); }
    finally { setLoading(''); }
  };

  const handleAutoEvolution = async () => {
    setLoading('evolution');
    try {
      const res = await triggerAutoEvolution();
      message.success(res.needs_evolution ? `发现进化需求: ${res.suggested_skill_name}` : '无进化需求');
    } catch { message.error('自动进化检查失败'); }
    finally { setLoading(''); }
  };

  const handleImportZip = async (file: File) => {
    setLoading('import');
    try {
      const res = await importSkillZip(file);
      await store.loadSkills();
      const skipped = res.skipped.length ? `，跳过 ${res.skipped.length} 个` : '';
      message.success(`已导入 ${res.imported.length} 个 Skill${skipped}`);
    } catch {
      message.error('Skill ZIP 导入失败');
    } finally {
      setLoading('');
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Upload
          accept=".zip"
          showUploadList={false}
          beforeUpload={(file) => {
            void handleImportZip(file as File);
            return false;
          }}
        >
          <Button icon={<UploadOutlined />} loading={loading === 'import'}>上传 Skill ZIP</Button>
        </Upload>
        <Button type="primary" loading={loading === 'verify'} onClick={handleVerify}>触发三Agent验证</Button>
        <Button loading={loading === 'evolution'} onClick={handleAutoEvolution}>触发自主进化</Button>
      </Space>
      {loading && <Spin tip="处理中..." />}
      <List
        grid={{ gutter: 16, column: 3 }}
        dataSource={store.skills}
        renderItem={(skill) => (
          <List.Item>
            <Card title={skill.name} size="small">
              <p style={{ fontSize: 13, color: '#666' }}>{skill.description}</p>
              <p style={{ fontSize: 12, color: '#999' }}>类别: {skill.category} | 访问: {skill.access}</p>
              <Button size="small" onClick={() => handleOptimize(skill.name)}>GEPA优化</Button>
            </Card>
          </List.Item>
        )}
      />
    </div>
  );
}
