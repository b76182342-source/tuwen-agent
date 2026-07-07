import React, { useEffect, useRef, useState } from 'react';
import {
  Card, Button, Space, Tag, message, Table, Modal, Form,
  InputNumber, Input, DatePicker, Descriptions, Statistic, Row, Col,
  Alert, Divider, Badge, Switch,
} from 'antd';
import {
  SyncOutlined, CheckCircleOutlined,
  CloseCircleOutlined, PlusOutlined, DeleteOutlined,
  ChromeOutlined, HeartOutlined, MessageOutlined, EyeOutlined,
  ShareAltOutlined, LineChartOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { publishApi, douyinSyncApi } from '@/services/api';
import type { PublishHistory, DouyinSyncRecord, HealthCheckResult } from '@/types';
import { usePresetCardStagger } from '@/hooks/useAnimations';

interface LocalRecord extends DouyinSyncRecord {
  key?: number;
}

const DouyinSync: React.FC = () => {
  const [healthStatus, setHealthStatus] = useState<HealthCheckResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [records, setRecords] = useState<LocalRecord[]>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [history, setHistory] = useState<PublishHistory[]>([]);
  const [showExtensionGuide, setShowExtensionGuide] = useState(false);
  const [autoSync, setAutoSync] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    checkHealth();
    loadHistory();
  }, []);

  // GSAP: 卡片交错入场
  usePresetCardStagger(containerRef, 'sync-card', 'sync');

  const checkHealth = async () => {
    setChecking(true);
    try {
      const { data } = await douyinSyncApi.healthCheck();
      setHealthStatus(data);
    } catch {
      message.error('检查后端状态失败');
    } finally {
      setChecking(false);
    }
  };

  const loadHistory = async () => {
    try {
      const { data } = await publishApi.getHistory();
      setHistory(data || []);
    } catch {
      console.error('加载发布历史失败');
    }
  };

  const handleAddRecord = () => {
    form.resetFields();
    form.setFieldsValue({ publish_time: dayjs() });
    setModalVisible(true);
  };

  const handleSaveRecord = async () => {
    const values = await form.validateFields();
    const newRecord: LocalRecord = {
      key: records.length + 1,
      text: values.text || '',
      tags: (values.tags || '').split(',').map((t: string) => t.trim()).filter(Boolean),
      publish_time: values.publish_time.format('YYYY-MM-DD HH:mm:ss'),
      views: values.views || 0,
      likes: values.likes || 0,
      comments: values.comments || 0,
      shares: values.shares || 0,
      favorites: values.favorites || 0,
      swipe_away_rate: (values.swipe_away_rate || 0) / 100,
      copy_expand_rate: (values.copy_expand_rate || 0) / 100,
      avg_images_viewed: values.avg_images_viewed || 0,
      fan_gain: values.fan_gain || 0,
      fan_loss: values.fan_loss || 0,
      fan_play_ratio: (values.fan_play_ratio || 0) / 100,
      engagement_rate: values.views > 0 ? (values.likes + values.comments) / values.views : 0,
      evaluation_score: values.evaluation_score || 0,
      evaluation_level: (values.evaluation_score || 0) >= 4 ? '较好' : '中等',
      source: 'manual',
    };
    setRecords([...records, newRecord]);
    setModalVisible(false);
  };

  const handleSubmitRecords = async () => {
    if (records.length === 0) {
      message.warning('请先添加记录');
      return;
    }
    setSyncing(true);
    try {
      const { data } = await douyinSyncApi.sync(
        records.map(r => ({
          ...r,
          engagement_rate: r.views > 0 ? (r.likes + r.comments) / r.views : 0,
        }))
      );
      if (data.success) {
        message.success(data.message);
        setRecords([]);
        loadHistory();
      } else {
        message.error(data.message);
      }
    } catch {
      message.error('提交失败');
    } finally {
      setSyncing(false);
    }
  };

  const removeRecord = (key: number) => {
    setRecords(records.filter((r) => r.key !== key));
  };

  const columns = [
    { title: '文案', dataIndex: 'text', ellipsis: true, width: 250 },
    { title: '标签', dataIndex: 'tags', render: (tags: string[]) => (
      <Space size={[0, 4]} wrap>{tags.map((t) => <Tag key={t}>{t}</Tag>)}</Space>
    )},
    { title: '发布时间', dataIndex: 'publish_time', width: 160 },
    { title: '点赞', dataIndex: 'likes', width: 80, render: (v: number) => (
      <span><HeartOutlined style={{ color: '#ff4d4f' }} /> {v}</span>
    )},
    { title: '评论', dataIndex: 'comments', width: 80, render: (v: number) => (
      <span><MessageOutlined style={{ color: '#2563eb' }} /> {v}</span>
    )},
    { title: '播放', dataIndex: 'views', width: 80, render: (v: number) => (
      <span><EyeOutlined style={{ color: '#52c41a' }} /> {v}</span>
    )},
    { title: '分享', dataIndex: 'shares', width: 80, render: (v: number) => (
      <span><ShareAltOutlined style={{ color: '#722ed1' }} /> {v}</span>
    )},
    { title: '互动率', dataIndex: 'engagement_rate', width: 80, render: (v: number) => (
      <span><LineChartOutlined style={{ color: '#faad14' }} /> {(v * 100).toFixed(2)}%</span>
    )},
    { title: '操作', key: 'action', width: 80,
      render: (_: any, r: LocalRecord) => (
        <Button type="link" danger icon={<DeleteOutlined />} onClick={() => removeRecord(r.key!)} />
      )},
  ];

  const historyColumns = [
    { title: '文案', dataIndex: 'text', ellipsis: true, width: 200 },
    { title: '发布时间', dataIndex: 'publish_time', width: 160 },
    { title: '点赞', dataIndex: 'likes', width: 80 },
    { title: '评论', dataIndex: 'comments', width: 80 },
    { title: '播放', dataIndex: 'views', width: 80 },
    { title: '互动率', dataIndex: 'engagement_rate', width: 80, render: (v: number) => `${(v * 100).toFixed(2)}%` },
    { title: '来源', dataIndex: 'source', width: 80, render: (v: string) => (
      <Tag color={v === 'extension' ? 'blue' : 'gray'}>
        {v === 'extension' ? '浏览器扩展' : '手动录入'}
      </Tag>
    )},
    { title: '评分', dataIndex: 'evaluation_level', width: 80, render: (v: string) => (
      <Tag color={v === '较好' || v === '很好' ? 'green' : v === '中等' ? 'orange' : 'red'}>{v}</Tag>
    )},
  ];

  return (
    <div ref={containerRef}>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card className="sync-card" title={<Space><CheckCircleOutlined />系统状态</Space>}
            extra={<Button loading={checking} onClick={checkHealth}>刷新</Button>}>
            {healthStatus ? (
              <Descriptions column={2} size="small">
                <Descriptions.Item label="服务状态">
                  {healthStatus.status === 'ok'
                    ? <Tag icon={<CheckCircleOutlined />} color="green">正常运行</Tag>
                    : <Tag icon={<CloseCircleOutlined />} color="red">异常</Tag>
                  }
                </Descriptions.Item>
                <Descriptions.Item label="服务版本">
                  {healthStatus.version}
                </Descriptions.Item>
                <Descriptions.Item label="抖音同步">
                  {healthStatus.features?.douyin_sync ? (
                    <Tag color="green">已启用</Tag>
                  ) : (
                    <Tag color="red">未启用</Tag>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="素材库">
                  {healthStatus.features?.material_library ? (
                    <Tag color="green">已启用</Tag>
                  ) : (
                    <Tag color="red">未启用</Tag>
                  )}
                </Descriptions.Item>
              </Descriptions>
            ) : <p>检查中...</p>}

            <Divider />

            <Space wrap>
              <Button icon={<ChromeOutlined />} onClick={() => setShowExtensionGuide(true)}>
                浏览器扩展指南
              </Button>
              <Button onClick={handleAddRecord} icon={<PlusOutlined />}>
                手动录入
              </Button>
            </Space>

            <div style={{ marginTop: 12 }}>
              <Alert
                message="💡 使用浏览器扩展导入数据"
                description="推荐安装浏览器扩展，从抖音创作中心自动提取发布数据，一键导入到系统，形成数据闭环。"
                type="info"
                showIcon
                closable
              />
            </div>
          </Card>
        </Col>

        <Col span={12}>
          <Card className="sync-card" title="数据概览">
            <Row gutter={16}>
              <Col span={6}>
                <Statistic title="待同步" value={records.length} suffix="条" />
              </Col>
              <Col span={6}>
                <Statistic title="已导入" value={history.length} suffix="条" />
              </Col>
              <Col span={6}>
                <Statistic title="总点赞"
                  value={history.reduce((s, r) => s + (r.likes || 0), 0)} />
              </Col>
              <Col span={6}>
                <Statistic title="总播放"
                  value={history.reduce((s, r) => s + (r.views || 0), 0)} />
              </Col>
            </Row>

            <Divider />

            <Space direction="vertical" style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>自动同步</span>
                <Switch checked={autoSync} onChange={(checked) => setAutoSync(checked)} />
              </div>
              <Button type="primary" size="large" block
                icon={<SyncOutlined />} loading={syncing}
                disabled={records.length === 0}
                onClick={handleSubmitRecords}>
                提交到数据库 ({records.length} 条)
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>

      <Card className="sync-card" title="待同步记录" extra={
        <Button icon={<PlusOutlined />} onClick={handleAddRecord}>添加记录</Button>
      }>
        <Table columns={columns} dataSource={records} rowKey="key"
          pagination={false} locale={{ emptyText: '暂无记录。点击"手动录入"添加，或安装浏览器扩展自动提取。' }} />
      </Card>

      <Card className="sync-card" title="已导入记录" extra={
        <Badge count={history.filter((h) => h.source === 'extension').length} offset={[0, 10]}>
          <span>扩展导入 {history.filter((h) => h.source === 'extension').length} 条</span>
        </Badge>
      }>
        <Table columns={historyColumns} dataSource={history} rowKey="id"
          pagination={{ pageSize: 10 }} locale={{ emptyText: '暂无导入记录' }} />
      </Card>

      <Modal title="添加发布记录" open={modalVisible}
        onOk={handleSaveRecord} onCancel={() => setModalVisible(false)} width={600}>
        <Form form={form} layout="vertical">
          <Form.Item name="text" label="文案" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="发布时的文案内容" />
          </Form.Item>
          <Form.Item name="tags" label="标签（逗号分隔）">
            <Input placeholder="#猫咪日常,#萌宠" />
          </Form.Item>
          <Form.Item name="publish_time" label="发布时间">
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={6}>
              <Form.Item name="views" label="播放量"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="likes" label="点赞数"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="comments" label="评论数"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="shares" label="分享数"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={6}>
              <Form.Item name="favorites" label="收藏量"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="swipe_away_rate" label="划走率(%)"><InputNumber min={0} max={100} step={0.1} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="copy_expand_rate" label="文案展开率(%)"><InputNumber min={0} max={100} step={0.1} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="avg_images_viewed" label="均浏览图片"><InputNumber min={0} step={0.1} style={{ width: '100%' }} /></Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="fan_gain" label="涨粉量"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="fan_loss" label="脱粉量"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="fan_play_ratio" label="粉丝播放占比(%)"><InputNumber min={0} max={100} step={0.01} style={{ width: '100%' }} /></Form.Item>
            </Col>
          </Row>
          <Form.Item name="evaluation_score" label="评估分数（1-5）">
            <InputNumber min={1} max={5} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="浏览器扩展安装指南" open={showExtensionGuide}
        onCancel={() => setShowExtensionGuide(false)} width={600} footer={null}>
        <div style={{ padding: 16 }}>
          <h3 style={{ marginBottom: 16 }}>📥 抖音创作中心数据导入助手</h3>

          <div style={{ marginBottom: 20 }}>
            <h4>1. 加载扩展</h4>
            <ol style={{ paddingLeft: 20, margin: 0 }}>
              <li>打开 Chrome 扩展管理页面：<code>chrome://extensions/</code></li>
              <li>启用右上角的"开发者模式"</li>
              <li>点击"加载已解压的扩展程序"</li>
              <li>选择文件夹：<code>D:\douyin-agent\browser-extension</code></li>
            </ol>
          </div>

          <div style={{ marginBottom: 20 }}>
            <h4>2. 使用方法</h4>
            <ol style={{ paddingLeft: 20, margin: 0 }}>
              <li>访问抖音创作中心：<a href="https://creator.douyin.com" target="_blank" rel="noopener noreferrer">creator.douyin.com</a></li>
              <li>点击页面右上角的"📥 导入到Agent"按钮</li>
              <li>预览数据后点击"确认导入"</li>
              <li>数据会自动同步到本系统</li>
            </ol>
          </div>

          <div style={{ marginBottom: 20 }}>
            <h4>3. 数据闭环</h4>
            <p>通过浏览器扩展，您可以：</p>
            <ul style={{ paddingLeft: 20, margin: 0 }}>
              <li>📊 将真实发布数据导入系统</li>
              <li>📈 分析内容表现和互动率</li>
              <li>🔄 形成创作→发布→分析→优化的闭环</li>
              <li>✅ 验证Agent建议的实际效果</li>
            </ul>
          </div>

          <div style={{ marginBottom: 20 }}>
            <h4>4. 注意事项</h4>
            <ul style={{ paddingLeft: 20, margin: 0 }}>
              <li>确保Agent后端正在运行（端口9000）</li>
              <li>扩展仅在抖音创作中心页面生效</li>
              <li>所有数据处理都在本地完成，不会上传到第三方</li>
            </ul>
          </div>

          <Button type="primary" onClick={() => setShowExtensionGuide(false)}>
            我知道了
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default DouyinSync;
