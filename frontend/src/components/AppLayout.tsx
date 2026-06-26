import React from 'react';
import { Layout, Menu } from 'antd';
import {
  EditOutlined,
  FolderOutlined,
  HistoryOutlined,
  BarChartOutlined,
  SyncOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';

const { Header, Content, Sider } = Layout;

const menuItems = [
  { key: '/workspace', icon: <EditOutlined />, label: '创作工作台' },
  { key: '/materials', icon: <FolderOutlined />, label: '素材库管理' },
  { key: '/history', icon: <HistoryOutlined />, label: '发布历史' },
  { key: '/analytics', icon: <BarChartOutlined />, label: '数据分析' },
  { key: '/sync', icon: <SyncOutlined />, label: '数据同步' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
];

interface AppLayoutProps {
  children: React.ReactNode;
}

const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ minHeight: '100vh', background: 'var(--color-surface-bg)' }}>
      {/* Header — 简洁暖白 */}
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 28px',
          background: '#FAF9F6',
          borderBottom: '1px solid #E7E5E4',
          position: 'sticky',
          top: 0,
          zIndex: 100,
          height: 52,
          lineHeight: '52px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: '#292524', letterSpacing: -0.3 }}>
            抖音图文创作 Agent
          </span>
        </div>
        <span style={{ color: '#A8A29E', fontSize: 13 }}>
          创作者主导 · 智能辅助
        </span>
      </Header>

      <Layout style={{ background: 'transparent' }}>
        {/* Sider — 暖白底 */}
        <Sider
          width={210}
          style={{
            background: 'transparent',
            paddingTop: 12,
            paddingLeft: 8,
            paddingRight: 8,
          }}
          breakpoint="lg"
          collapsedWidth={0}
        >
          <Menu
            mode="inline"
            selectedKeys={[location.pathname === '/' ? '/workspace' : location.pathname]}
            style={{
              background: 'transparent',
              border: 'none',
              fontWeight: 500,
              fontSize: 14,
            }}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
          />
        </Sider>

        {/* Content — 暖白底 + 白色卡片 */}
        <Layout style={{ background: 'transparent', padding: '12px 24px 20px 8px' }}>
          <Content
            style={{
              padding: 24,
              margin: 0,
              minHeight: 280,
              background: '#FFFFFF',
              borderRadius: 14,
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}
          >
            {children}
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
};

export default AppLayout;
