import React, { useEffect, useState } from 'react';
import {
  Card,
  Descriptions,
  Tag,
  Space,
  Switch,
  Button,
  Modal,
  message,
} from 'antd';
import {
  ApiOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PoweroffOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import api from '@/services/api';

const MOCK_MODE_KEY = 'settings_mock_mode';

const Settings: React.FC = () => {
  const [mockMode, setMockMode] = useState<boolean>(
    () => localStorage.getItem(MOCK_MODE_KEY) === 'true'
  );
  const [testingDeepSeek, setTestingDeepSeek] = useState(false);
  const [testingUnsplash, setTestingUnsplash] = useState(false);
  const [testingPexels, setTestingPexels] = useState(false);
  const [deepSeekStatus, setDeepSeekStatus] = useState<boolean | null>(null);
  const [unsplashStatus, setUnsplashStatus] = useState<boolean | null>(null);
  const [pexelsStatus, setPexelsStatus] = useState<boolean | null>(null);

  useEffect(() => {
    localStorage.setItem(MOCK_MODE_KEY, String(mockMode));
    message.info(mockMode ? '已切换到 Mock 模式' : '已切换到 API 模式');
  }, [mockMode]);

  const testConnection = async (
    service: string,
    setTesting: (v: boolean) => void,
    setStatus: (v: boolean | null) => void
  ) => {
    setTesting(true);
    setStatus(null);
    try {
      const resp = await api.get('/health', { params: { service }, timeout: 10000 });
      if (resp.data?.status === 'ok' || resp.status === 200) {
        setStatus(true);
        message.success(`${service} 连接正常`);
      } else {
        setStatus(false);
        message.warning(`${service} 响应异常`);
      }
    } catch {
      setStatus(false);
      message.error(`${service} 连接失败`);
    } finally {
      setTesting(false);
    }
  };

  const handleClearAllData = () => {
    Modal.confirm({
      title: '确认清除所有数据',
      icon: <ExclamationCircleOutlined />,
      content: '此操作将清除所有 localStorage 数据、对话记录缓存和本地素材。此操作不可撤销！',
      okText: '确认清除',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => {
        localStorage.clear();
        message.success('所有本地数据已清除，页面即将刷新');
        setTimeout(() => window.location.reload(), 1500);
      },
    });
  };

  const renderStatusBadge = (status: boolean | null, testing: boolean, _label: string) => {
    if (testing) return <Tag icon={<LoadingOutlined spin />} color="processing">检测中...</Tag>;
    if (status === true) return <Tag icon={<CheckCircleOutlined />} color="green">已配置</Tag>;
    if (status === false) return <Tag icon={<CloseCircleOutlined />} color="red">未配置</Tag>;
    return <Tag icon={<CloseCircleOutlined />} color="default">未检测</Tag>;
  };

  return (
    <div>
      <Card title={<Space><SettingOutlined />系统设置</Space>} style={{ marginBottom: 24 }}>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="后端 API 状态">
            <Space>
              <Tag color={mockMode ? 'orange' : 'green'}>
                {mockMode ? 'Mock 模式' : 'API 模式'}
              </Tag>
              <span>Mock 模式</span>
              <Switch
                checked={mockMode}
                onChange={setMockMode}
                checkedChildren="开"
                unCheckedChildren="关"
              />
            </Space>
            <div style={{ marginTop: 4, color: '#888' }}>
              {mockMode ? '使用本地模拟数据（后端不可用时）' : '连接后端 API 服务'}
            </div>
          </Descriptions.Item>
          <Descriptions.Item label="DeepSeek API">
            <Space>
              {renderStatusBadge(deepSeekStatus, testingDeepSeek, 'DeepSeek')}
              <Button
                size="small"
                icon={testingDeepSeek ? <LoadingOutlined /> : <PoweroffOutlined />}
                loading={testingDeepSeek}
                onClick={() => testConnection('deepseek', setTestingDeepSeek, setDeepSeekStatus)}
              >
                测试连接
              </Button>
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="Unsplash API">
            <Space>
              {renderStatusBadge(unsplashStatus, testingUnsplash, 'Unsplash')}
              <Button
                size="small"
                icon={testingUnsplash ? <LoadingOutlined /> : <PoweroffOutlined />}
                loading={testingUnsplash}
                onClick={() => testConnection('unsplash', setTestingUnsplash, setUnsplashStatus)}
              >
                测试连接
              </Button>
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="Pexels API">
            <Space>
              {renderStatusBadge(pexelsStatus, testingPexels, 'Pexels')}
              <Button
                size="small"
                icon={testingPexels ? <LoadingOutlined /> : <PoweroffOutlined />}
                loading={testingPexels}
                onClick={() => testConnection('pexels', setTestingPexels, setPexelsStatus)}
              >
                测试连接
              </Button>
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="抖音开放平台">
            <Tag icon={<CloseCircleOutlined />} color="default">未配置</Tag>
            <span style={{ marginLeft: 8, color: '#888' }}>DOUYIN_CLIENT_KEY 未设置</span>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title={<Space><ApiOutlined />API 端点</Space>} style={{ marginBottom: 24 }}>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="Agent 执行">
            <Tag>POST /api/agent/run</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="执行状态">
            <Tag>GET /api/agent/status/:id</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="回滚操作">
            <Tag>POST /api/agent/rollback</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="素材管理">
            <Tag>GET|POST|PUT|DELETE /api/materials</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="发布历史">
            <Tag>GET|DELETE /api/publish</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="数据分析">
            <Tag>GET /api/analytics/overview</Tag>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="危险操作" style={{ borderColor: '#ff4d4f' }}>
        <Button
          danger
          icon={<DeleteOutlined />}
          onClick={handleClearAllData}
        >
          清除所有数据
        </Button>
        <div style={{ marginTop: 8, color: '#999' }}>
          清除 localStorage、对话缓存和本地存储的素材数据
        </div>
      </Card>
    </div>
  );
};

export default Settings;