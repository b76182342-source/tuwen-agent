import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, App } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { TextPlugin } from 'gsap/TextPlugin';

gsap.registerPlugin(ScrollTrigger, TextPlugin);
import AppLayout from '@/components/AppLayout';
import Workspace from '@/pages/Workspace';
import MaterialLibrary from '@/pages/MaterialLibrary';
import PublishHistory from '@/pages/PublishHistory';
import Analytics from '@/pages/Analytics';
import Settings from '@/pages/Settings';
import DouyinSync from '@/pages/DouyinSync';
import './index.css';

// ============================================================
// 暖白极简主题 — Ant Design
// ============================================================
const themeConfig = {
  token: {
    // 主色：暖琥珀
    colorPrimary: '#D97706',
    colorSuccess: '#059669',
    colorWarning: '#D97706',
    colorError: '#DC2626',
    colorInfo: '#78716C',
    // 文字
    colorTextBase: '#292524',
    colorTextSecondary: '#78716C',
    colorTextTertiary: '#A8A29E',
    colorTextQuaternary: '#D6D3D1',
    // 背景
    colorBgBase: '#FFFFFF',
    colorBgContainer: '#FFFFFF',
    colorBgLayout: '#FAF9F6',
    colorBgElevated: '#FFFFFF',
    colorBgSpotlight: '#292524',
    // 边框
    colorBorder: '#E7E5E4',
    colorBorderSecondary: '#F5F5F4',
    // 填充
    colorFillQuaternary: '#FAF9F6',
    // 圆角
    borderRadius: 10,
    borderRadiusLG: 14,
    borderRadiusSM: 8,
    borderRadiusXS: 6,
    // 字体
    fontSize: 14,
    fontSizeLG: 16,
    fontSizeXL: 20,
    fontFamily: `-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', Roboto, sans-serif`,
    // 阴影
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
    boxShadowSecondary: '0 4px 16px rgba(0,0,0,0.06)',
    // 其他
    controlHeight: 36,
    lineHeight: 1.6,
    wireframe: false,
    colorLink: '#D97706',
  },
  components: {
    Button: {
      borderRadius: 10,
      controlHeight: 36,
      fontWeight: 500,
      primaryShadow: '0 2px 8px rgba(217,119,6,0.2)',
    },
    Card: {
      borderRadius: 14,
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
    },
    Tag: {
      borderRadius: 6,
    },
    Input: {
      borderRadius: 10,
      controlHeight: 36,
      activeShadow: '0 0 0 2px rgba(217,119,6,0.1)',
    },
    Menu: {
      itemBorderRadius: 10,
      itemMarginInline: 8,
      itemHeight: 40,
      itemSelectedBg: '#FFF7ED',
      itemSelectedColor: '#D97706',
    },
    Table: {
      borderRadius: 12,
      headerBg: '#FAF9F6',
    },
    Modal: {
      borderRadius: 16,
    },
    Steps: {
      iconSize: 28,
    },
    Progress: {
      defaultColor: '#D97706',
    },
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      <App>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <AppLayout>
            <Routes>
              <Route path="/" element={<Workspace />} />
              <Route path="/workspace" element={<Workspace />} />
              <Route path="/materials" element={<MaterialLibrary />} />
              <Route path="/history" element={<PublishHistory />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/sync" element={<DouyinSync />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </AppLayout>
        </BrowserRouter>
      </App>
    </ConfigProvider>
  </React.StrictMode>
);
