/**
 * 发布历史页 v2 — 对齐抖音数据维度
 */
import React, { useEffect, useRef, useState } from 'react';
import { Card, Table, Tag, Button, Space, Modal, Descriptions, Statistic, Row, Col, App } from 'antd';
import {
  EyeOutlined, LikeOutlined, ReloadOutlined, DeleteOutlined,
  TrophyOutlined, RiseOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { publishApi } from '@/services/api';
import type { PublishHistory } from '@/types';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { usePresetCardStagger } from '@/hooks/useAnimations';

const CHART = { likes: '#059669', views: '#2563EB', comments: '#78716C' };

const PublishHistoryPage: React.FC = () => {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [history, setHistory] = useState<PublishHistory[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<PublishHistory | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    publishApi.getHistory()
      .then(r => setHistory(r.data || []))
      .catch(() => message.error('获取发布历史失败'))
      .finally(() => setLoading(false));
  }, []);

  // GSAP: 卡片交错入场（数据加载完成后触发）
  usePresetCardStagger(containerRef, 'history-card', 'history', { ready: !loading });

  const handleDelete = (item: PublishHistory) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除"${item.text?.slice(0, 30)}..."吗？`,
      onOk: async () => {
        try { await publishApi.delete(item.id); message.success('删除成功'); }
        catch { message.warning('删除失败，已从本地列表移除'); }
        setHistory(prev => prev.filter(h => h.id !== item.id));
      },
    });
  };

  const handleRepublish = (item: PublishHistory) => {
    localStorage.setItem('republish_data', JSON.stringify(item));
    message.success('已跳转到创作工作台');
    navigate('/workspace');
  };

  const totalViews = history.reduce((s, h) => s + (h.views || 0), 0);
  const totalLikes = history.reduce((s, h) => s + (h.likes || 0), 0);
  const totalFanGain = history.reduce((s, h) => s + (h.fan_gain || 0), 0);

  const chartData = history.slice(-20).map(item => ({
    name: item.publish_time?.slice(0, 10) || '',
    views: item.views || 0,
    likes: item.likes || 0,
    comments: item.comments || 0,
  }));

  const columns = [
    { title: '文案', dataIndex: 'text', ellipsis: true, width: 200 },
    { title: '发布时间', dataIndex: 'publish_time', width: 130, render: (v: string) => v?.slice(0, 16) || '-' },
    { title: '播放', dataIndex: 'views', width: 70, render: (v: number) => (<span><EyeOutlined /> {v || 0}</span>) },
    { title: '点赞', dataIndex: 'likes', width: 70, render: (v: number) => (<span style={{ color: '#ff4d4f' }}><LikeOutlined /> {v || 0}</span>) },
    { title: '评论', dataIndex: 'comments', width: 70 },
    { title: '分享', dataIndex: 'shares', width: 60 },
    { title: '收藏', dataIndex: 'favorites', width: 60 },
    { title: '划走率', dataIndex: 'swipe_away_rate', width: 70, render: (v: number) => v ? `${(v * 100).toFixed(0)}%` : '-' },
    { title: '涨粉', dataIndex: 'fan_gain', width: 60, render: (v: number) => (<span style={{ color: '#059669' }}><RiseOutlined /> {v || 0}</span>) },
    { title: '来源', dataIndex: 'source', width: 70, render: (v: string) => (
      <Tag color={v === 'extension' ? 'cyan' : v === 'agent' ? 'purple' : 'default'}>
        {v === 'extension' ? '扩展' : v === 'agent' ? 'Agent' : '手动'}
      </Tag>
    )},
    { title: '评分', dataIndex: 'evaluation_score', width: 60, render: (v: number) => (
      <Tag color={v >= 4 ? 'cyan' : v >= 3 ? 'orange' : 'red'}>{v?.toFixed(1) || '-'}</Tag>
    )},
    { title: '操作', key: 'action', width: 120,
      render: (_: any, r: PublishHistory) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => { setSelected(r); setDetailOpen(true); }}>详情</Button>
          <Button type="link" size="small" icon={<ReloadOutlined />} onClick={() => handleRepublish(r)} />
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)} />
        </Space>
      )},
  ];

  return (
    <div ref={containerRef}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '总内容', value: history.length, icon: <TrophyOutlined />, color: '#2563EB' },
          { title: '总播放', value: totalViews, icon: <EyeOutlined />, color: '#2563EB' },
          { title: '总点赞', value: totalLikes, icon: <LikeOutlined />, color: '#059669' },
          { title: '总涨粉', value: totalFanGain, icon: <RiseOutlined />, color: '#7c4dff' },
        ].map(c => (
          <Col span={6} key={c.title}>
            <Card size="small" className="history-card">
              <Statistic title={c.title} value={c.value} prefix={c.icon} valueStyle={{ color: c.color, fontSize: 20, fontWeight: 700 }} />
            </Card>
          </Col>
        ))}
      </Row>

      <Card title="📈 播放/点赞/评论趋势" size="small" className="history-card" style={{ marginBottom: 16 }}>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#555568' }} />
              <YAxis tick={{ fontSize: 11, fill: '#555568' }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="views" stroke={CHART.views} name="播放" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="likes" stroke={CHART.likes} name="点赞" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="comments" stroke={CHART.comments} name="评论" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ color: '#555568', textAlign: 'center', padding: 24 }}>暂无数据</div>
        )}
      </Card>

      <Card title="📋 发布历史" loading={loading} className="history-card">
        <Table columns={columns} dataSource={history} rowKey="id"
          pagination={{ pageSize: 20 }} size="small" scroll={{ x: 1200 }}
          locale={{ emptyText: '暂无发布记录。前往"数据同步"页导入数据。' }} />
      </Card>

      <Modal title="发布详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={750}>
        {selected && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="文案" span={2}>{selected.text}</Descriptions.Item>
            <Descriptions.Item label="发布时间">{selected.publish_time}</Descriptions.Item>
            <Descriptions.Item label="来源">
              <Tag color={selected.source === 'extension' ? 'cyan' : selected.source === 'agent' ? 'purple' : 'default'}>
                {selected.source === 'extension' ? '浏览器扩展' : selected.source === 'agent' ? 'Agent生成' : '手动录入'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="播放量">{selected.views}</Descriptions.Item>
            <Descriptions.Item label="点赞数">{selected.likes}</Descriptions.Item>
            <Descriptions.Item label="评论数">{selected.comments}</Descriptions.Item>
            <Descriptions.Item label="分享数">{selected.shares}</Descriptions.Item>
            <Descriptions.Item label="收藏数">{selected.favorites}</Descriptions.Item>
            <Descriptions.Item label="划走率">{((selected.swipe_away_rate || 0) * 100).toFixed(1)}%</Descriptions.Item>
            <Descriptions.Item label="文案展开率">{((selected.copy_expand_rate || 0) * 100).toFixed(1)}%</Descriptions.Item>
            <Descriptions.Item label="平均浏览图片">{selected.avg_images_viewed}</Descriptions.Item>
            <Descriptions.Item label="涨粉量">{selected.fan_gain}</Descriptions.Item>
            <Descriptions.Item label="脱粉量">{selected.fan_loss}</Descriptions.Item>
            <Descriptions.Item label="粉丝播放占比">{((selected.fan_play_ratio || 0) * 100).toFixed(1)}%</Descriptions.Item>
            <Descriptions.Item label="评估分数">{selected.evaluation_score?.toFixed(1)}</Descriptions.Item>
            <Descriptions.Item label="评估等级">{selected.evaluation_level}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default PublishHistoryPage;
